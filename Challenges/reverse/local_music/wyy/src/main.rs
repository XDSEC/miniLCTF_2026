use aes::cipher::{BlockEncryptMut, KeyInit, block_padding::Pkcs7};
use anyhow::{Context, Result, anyhow, bail};
use base64::{Engine, engine::general_purpose::STANDARD as base64};
use clap::{Args, Parser, Subcommand};
use ecb::Encryptor;
use id3::{Tag, TagLike, frame::Content};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

include!(concat!(env!("OUT_DIR"), "/build_consts.rs"));

type Aes128EcbEnc = Encryptor<aes::Aes128>;

const HEADER: &[u8; 10] = b"MINILCTF\0\0";
const KEY_PREFIX: &[u8] = b"miniL-audio-key";
const META_PREFIX: &[u8] = b"miniL:";
const COMMENT_PREFIX: &[u8] = b"miniL meta:";
const KEY_SEED_PREFIX: &[u8] = b"KaguyaIrohaYachiyo";
const BUCKET_SCALE: u64 = 10_000;

#[derive(Debug, Parser)]
#[command(version, about = "Pack an audio file into a wyy challenge container")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Pack(PackOpts),
}

#[derive(Debug, Args)]
struct PackOpts {
    #[arg(value_name = "audio")]
    audio_path: PathBuf,
    #[arg(value_name = "output.wyy")]
    output_path: PathBuf,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let Command::Pack(opts) = cli.command;

    let audio = fs::read(&opts.audio_path)?;
    let extracted = extract_audio_side_data(&audio)?;
    write_package_with_converged_timestamp(
        &audio,
        &extracted.meta_json,
        extracted.image.as_deref(),
        &opts.output_path,
    )?;

    println!("{}", opts.output_path.display());
    Ok(())
}

fn write_package_with_converged_timestamp(
    audio: &[u8],
    meta_json: &[u8],
    image: Option<&[u8]>,
    output_path: &Path,
) -> Result<u64> {
    let mut ts = now_secs()? + 2;
    for _ in 0..8 {
        let package = pack(audio, meta_json, image, ts)?;
        wait_until(ts)?;
        fs::write(output_path, package)?;
        let real = mtime_secs(output_path)?;
        if real == ts {
            return Ok(real);
        }
        ts = real + 2;
    }
    bail!("timestamp did not converge")
}

fn pack(audio: &[u8], meta_json: &[u8], image: Option<&[u8]>, ts: u64) -> Result<Vec<u8>> {
    let (core_key, meta_key) = derive_keys(ts);
    let audio_key = derive_audio_key(&core_key);

    let mut out =
        Vec::with_capacity(audio.len() + meta_json.len() + image.map_or(0, <[u8]>::len) + 256);
    out.extend_from_slice(HEADER);
    write_frame(&mut out, &encrypt_key_frame(&core_key, &audio_key)?)?;
    write_frame(&mut out, &encrypt_comment_frame(&meta_key, meta_json)?)?;
    out.extend_from_slice(&[0u8; 5]);

    let image = image.unwrap_or_default();
    write_u32(&mut out, image.len())?;
    write_frame(&mut out, image)?;

    let mut encrypted_audio = audio.to_vec();
    xor_audio(&mut encrypted_audio, &audio_key);
    out.extend_from_slice(&encrypted_audio);
    Ok(out)
}

fn derive_keys(ts: u64) -> ([u8; 16], [u8; 16]) {
    assert!(TIME_BUCKET_MIN <= ts / BUCKET_SCALE && ts / BUCKET_SCALE <= TIME_BUCKET_MAX);

    let digest = Sha256::digest([KEY_SEED_PREFIX, ts.to_string().as_bytes()].concat());
    let mut core_key = [0u8; 16];
    let mut meta_key = [0u8; 16];
    core_key.copy_from_slice(&digest[..16]);
    meta_key.copy_from_slice(&digest[16..32]);
    (core_key, meta_key)
}

fn encrypt_key_frame(key: &[u8; 16], audio_key: &[u8]) -> Result<Vec<u8>> {
    let mut plain = Vec::with_capacity(KEY_PREFIX.len() + audio_key.len());
    plain.extend_from_slice(KEY_PREFIX);
    plain.extend_from_slice(audio_key);

    let mut encrypted = aes_encrypt(&plain, key)?;
    encrypted.iter_mut().for_each(|byte| *byte ^= 100);
    Ok(encrypted)
}

fn encrypt_comment_frame(key: &[u8; 16], meta_json: &[u8]) -> Result<Vec<u8>> {
    let mut plain = Vec::with_capacity(META_PREFIX.len() + meta_json.len());
    plain.extend_from_slice(META_PREFIX);
    plain.extend_from_slice(meta_json);

    let encrypted = aes_encrypt(&plain, key)?;
    let mut comment = Vec::with_capacity(COMMENT_PREFIX.len() + encrypted.len() * 4 / 3 + 4);
    comment.extend_from_slice(COMMENT_PREFIX);
    comment.extend_from_slice(base64.encode(encrypted).as_bytes());
    comment.iter_mut().for_each(|byte| *byte ^= 99);
    Ok(comment)
}

fn aes_encrypt(data: &[u8], key: &[u8; 16]) -> Result<Vec<u8>> {
    let cipher = Aes128EcbEnc::new(key.into());
    let mut buffer = vec![0u8; ((data.len() / 16) + 1) * 16];
    buffer[..data.len()].copy_from_slice(data);
    let encrypted = cipher
        .encrypt_padded_mut::<Pkcs7>(&mut buffer, data.len())
        .map_err(|_| anyhow!("aes padding"))?;
    Ok(encrypted.to_vec())
}

fn derive_audio_key(seed: &[u8; 16]) -> Vec<u8> {
    let mut key = Vec::with_capacity(64);
    for round in 0..4u8 {
        for (i, byte) in seed.iter().enumerate() {
            key.push(
                byte.rotate_left(((i as u32) + (round as u32)) & 7)
                    .wrapping_add(0x31u8.wrapping_mul(round.wrapping_add(1)))
                    ^ (i as u8).wrapping_mul(0x17),
            );
        }
    }
    key
}

fn xor_audio(data: &mut [u8], key: &[u8]) {
    data.iter_mut()
        .zip(NcmRc4::new(key).into_iter().cycle())
        .for_each(|(byte, mask)| *byte ^= mask);
}

fn extract_audio_side_data(audio: &[u8]) -> Result<ExtractedSideData> {
    if audio.starts_with(b"fLaC") {
        return extract_flac_side_data(audio);
    }
    if audio.starts_with(b"ID3") || audio.starts_with(&[0xFF, 0xFB]) {
        return extract_mp3_side_data(audio);
    }
    bail!("unsupported audio format")
}

fn extract_flac_side_data(audio: &[u8]) -> Result<ExtractedSideData> {
    let mut pos = 4;
    let mut tags = Vec::new();
    let mut image = None;

    loop {
        let header = audio[pos];
        pos += 1;
        let len = be24(&audio[pos..pos + 3]) as usize;
        pos += 3;
        let block = slice(audio, &mut pos, len)?;

        match header & 0x7f {
            4 => tags.extend(parse_vorbis_comments(block)?),
            6 => {
                let candidate = parse_picture_block(block)?;
                if image.as_ref().is_none_or(|current: &PictureBlock| {
                    current.picture_type != 3 && candidate.picture_type == 3
                }) {
                    image = Some(candidate);
                }
            }
            _ => {}
        }

        if header & 0x80 != 0 {
            break;
        }
    }

    Ok(ExtractedSideData {
        meta_json: build_metadata_json(&tags, "flac").into_bytes(),
        image: image.map(|picture| picture.data),
    })
}

fn extract_mp3_side_data(audio: &[u8]) -> Result<ExtractedSideData> {
    let tag = Tag::read_from2(std::io::Cursor::new(audio))?;
    let mut tags = Vec::new();

    if let Some(title) = tag.title() {
        tags.push(("TITLE".to_owned(), title.to_owned()));
    }
    if let Some(artist) = tag.artist() {
        tags.push(("ARTIST".to_owned(), artist.to_owned()));
    }
    if let Some(album) = tag.album() {
        tags.push(("ALBUM".to_owned(), album.to_owned()));
    }
    if let Some(comment) = first_comment(&tag) {
        tags.push(("COMMENT".to_owned(), comment));
    }

    for frame in tag.frames() {
        if let Content::Text(text) = frame.content() {
            if !frame.id().is_empty() {
                tags.push((frame.id().to_owned(), text.to_owned()));
            }
        }
    }

    let image = tag.pictures().next().map(|picture| picture.data.clone());

    Ok(ExtractedSideData {
        meta_json: build_metadata_json(&tags, "mp3").into_bytes(),
        image,
    })
}

#[derive(Debug)]
struct ExtractedSideData {
    meta_json: Vec<u8>,
    image: Option<Vec<u8>>,
}

fn parse_vorbis_comments(block: &[u8]) -> Result<Vec<(String, String)>> {
    let mut pos = 0;
    let vendor_len = le_u32(block, &mut pos)? as usize;
    let _ = slice(block, &mut pos, vendor_len)?;
    let count = le_u32(block, &mut pos)? as usize;

    let mut tags = Vec::with_capacity(count);
    for _ in 0..count {
        let len = le_u32(block, &mut pos)? as usize;
        let entry = std::str::from_utf8(slice(block, &mut pos, len)?)?;
        if let Some((key, value)) = entry.split_once('=') {
            tags.push((key.to_owned(), value.to_owned()));
        }
    }
    Ok(tags)
}

#[derive(Debug)]
struct PictureBlock {
    picture_type: u32,
    data: Vec<u8>,
}

fn parse_picture_block(block: &[u8]) -> Result<PictureBlock> {
    let mut pos = 0;
    let picture_type = be_u32(block, &mut pos)?;
    let mime_len = be_u32(block, &mut pos)? as usize;
    let _ = slice(block, &mut pos, mime_len)?;
    let desc_len = be_u32(block, &mut pos)? as usize;
    let _ = slice(block, &mut pos, desc_len)?;
    for _ in 0..4 {
        let _ = be_u32(block, &mut pos)?;
    }
    let data_len = be_u32(block, &mut pos)? as usize;
    Ok(PictureBlock {
        picture_type,
        data: slice(block, &mut pos, data_len)?.to_vec(),
    })
}

fn build_metadata_json(tags: &[(String, String)], format_name: &str) -> String {
    let title = tag(tags, "TITLE");
    let artist = tag(tags, "ARTIST").or_else(|| tag(tags, "ALBUM_ARTIST"));
    let album = tag(tags, "ALBUM");
    let comment = tag(tags, "COMMENT");

    let mut json = format!(
        "{{\"musicName\":\"{}\",\"artist\":\"{}\",\"album\":\"{}\",\"comment\":\"{}\",\"format\":\"flac\",\"sourceTags\":{{",
        escape_json(title.unwrap_or_default()),
        escape_json(artist.unwrap_or_default()),
        escape_json(album.unwrap_or_default()),
        escape_json(comment.unwrap_or_default()),
    );
    json = json.replacen(
        "\"format\":\"flac\"",
        &format!("\"format\":\"{format_name}\""),
        1,
    );

    for (i, (key, value)) in tags.iter().enumerate() {
        if i > 0 {
            json.push(',');
        }
        json.push('"');
        json.push_str(&escape_json(key));
        json.push_str("\":\"");
        json.push_str(&escape_json(value));
        json.push('"');
    }

    json.push_str("}}");
    json
}

fn first_comment(tag: &Tag) -> Option<String> {
    tag.frames().find_map(|frame| match frame.content() {
        Content::Comment(comment) => Some(comment.text.clone()),
        _ => None,
    })
}

fn tag<'a>(tags: &'a [(String, String)], name: &str) -> Option<&'a str> {
    tags.iter()
        .find(|(key, _)| key.eq_ignore_ascii_case(name))
        .map(|(_, value)| value.as_str())
}

fn escape_json(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for ch in input.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => {
                let _ = std::fmt::Write::write_fmt(&mut out, format_args!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out
}

fn slice<'a>(buf: &'a [u8], pos: &mut usize, len: usize) -> Result<&'a [u8]> {
    let out = buf.get(*pos..*pos + len).context("bad flac")?;
    *pos += len;
    Ok(out)
}

fn le_u32(buf: &[u8], pos: &mut usize) -> Result<u32> {
    Ok(u32::from_le_bytes(slice(buf, pos, 4)?.try_into().unwrap()))
}

fn be_u32(buf: &[u8], pos: &mut usize) -> Result<u32> {
    Ok(u32::from_be_bytes(slice(buf, pos, 4)?.try_into().unwrap()))
}

fn be24(buf: &[u8]) -> u32 {
    ((buf[0] as u32) << 16) | ((buf[1] as u32) << 8) | buf[2] as u32
}

fn write_frame(out: &mut Vec<u8>, data: &[u8]) -> Result<()> {
    write_u32(out, data.len())?;
    out.write_all(data)?;
    Ok(())
}

fn write_u32(out: &mut Vec<u8>, value: usize) -> Result<()> {
    out.write_all(&u32::try_from(value)?.to_le_bytes())?;
    Ok(())
}

fn now_secs() -> Result<u64> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

fn mtime_secs(path: &Path) -> Result<u64> {
    Ok(fs::metadata(path)?
        .modified()?
        .duration_since(UNIX_EPOCH)?
        .as_secs())
}

fn wait_until(target: u64) -> Result<()> {
    loop {
        let now = now_secs()?;
        if now >= target {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(((target - now) * 1000).min(200)));
    }
}

#[derive(Debug, Clone)]
struct NcmRc4 {
    state: [u8; 256],
}

impl NcmRc4 {
    fn new(key: &[u8]) -> Self {
        let mut rc4 = NcmRc4 { state: [0; 256] };
        rc4.ncm_prga(&Self::ksa(key));
        rc4
    }

    fn ksa(key: &[u8]) -> [u8; 256] {
        let mut state = [0; 256];
        state.iter_mut().enumerate().for_each(|(i, x)| *x = i as u8);

        let mut j = 0u8;
        for (i, k) in (0..=255usize).zip(key.iter().cycle()) {
            j = j.wrapping_add(state[i]).wrapping_add(*k);
            state.swap(i, j.into());
        }
        state
    }

    fn ncm_prga(&mut self, state: &[u8; 256]) {
        for i in 0..=255u8 {
            let key1 = i.wrapping_add(1);
            let key2 = key1.wrapping_add(state[key1 as usize]);
            let index = state[key1 as usize].wrapping_add(state[key2 as usize]);
            self.state[i as usize] = state[index as usize];
        }
    }
}

impl IntoIterator for NcmRc4 {
    type Item = u8;
    type IntoIter = std::array::IntoIter<u8, 256>;

    fn into_iter(self) -> Self::IntoIter {
        self.state.into_iter()
    }
}

#[cfg(test)]
mod tests;
