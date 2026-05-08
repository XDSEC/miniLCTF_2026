use super::*;
use aes::cipher::{BlockDecryptMut, KeyInit};
use ecb::Decryptor;
use std::{
    io::{Cursor, Read},
    panic,
};

type Aes128EcbDec = Decryptor<aes::Aes128>;

#[test]
fn extracts_tags_and_cover() -> Result<()> {
    let picture = b"\xff\xd8\xffcover";
    let flac = build_test_flac(
        &[
            ("TITLE", "Star Door"),
            ("ARTIST", "Kaguya"),
            ("COMMENT", "Look at the spectrum."),
        ],
        Some(picture),
        b"audio",
    );

    let extracted = extract_flac_side_data(&flac)?;
    let meta = String::from_utf8(extracted.meta_json)?;
    assert!(meta.contains("\"musicName\":\"Star Door\""));
    assert!(meta.contains("\"COMMENT\":\"Look at the spectrum.\""));
    assert_eq!(extracted.image.as_deref(), Some(picture.as_slice()));
    Ok(())
}

#[test]
fn roundtrip_package() -> Result<()> {
    let picture = b"\x89PNG\r\n\x1a\nminiL";
    let flac = build_test_flac(
        &[
            ("TITLE", "Princess Kaguya Across Spacetime"),
            ("ARTIST", "Kaguya;Iroha;Yachiyo"),
            ("ALBUM", "miniLCTF_2026"),
            ("COMMENT", "Spectrum only."),
        ],
        Some(picture),
        b"fake flac audio body",
    );
    let extracted = extract_flac_side_data(&flac)?;
    let ts = valid_test_timestamp();
    let package = pack(&flac, &extracted.meta_json, extracted.image.as_deref(), ts)?;
    let decoded = decode_for_test(&package, ts)?;

    assert_eq!(decoded.audio, flac);
    assert_eq!(decoded.meta, extracted.meta_json);
    assert_eq!(decoded.image, picture);
    Ok(())
}

#[test]
fn wrong_timestamp_fails() -> Result<()> {
    let flac = build_test_flac(
        &[("TITLE", "Kaguya"), ("COMMENT", "No direct flag.")],
        None,
        b"audio",
    );
    let extracted = extract_flac_side_data(&flac)?;
    let ts = valid_test_timestamp();
    let package = pack(&flac, &extracted.meta_json, extracted.image.as_deref(), ts)?;
    assert!(decode_for_test(&package, ts + 1).is_err());
    Ok(())
}

#[test]
fn timestamp_guard_is_active() {
    let bad = TIME_BUCKET_MIN
        .checked_sub(1)
        .map(|bucket| bucket * BUCKET_SCALE)
        .unwrap_or((TIME_BUCKET_MAX + 1) * BUCKET_SCALE);
    assert!(panic::catch_unwind(|| derive_keys(bad)).is_err());
}

#[test]
fn write_path_uses_real_mtime() -> Result<()> {
    let flac = build_test_flac(
        &[("TITLE", "Kaguya"), ("COMMENT", "Spectrum only.")],
        Some(b"cover"),
        b"audio body",
    );
    let extracted = extract_flac_side_data(&flac)?;
    let path = std::env::temp_dir().join(format!(
        "wyy-test-{}-{}.wyy",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    ));

    let ts = write_package_with_converged_timestamp(
        &flac,
        &extracted.meta_json,
        extracted.image.as_deref(),
        &path,
    )?;
    let package = fs::read(&path)?;
    let decoded = decode_for_test(&package, ts)?;

    assert_eq!(ts, mtime_secs(&path)?);
    assert_eq!(decoded.audio, flac);
    let _ = fs::remove_file(path);
    Ok(())
}

struct Decoded {
    audio: Vec<u8>,
    meta: Vec<u8>,
    image: Vec<u8>,
}

fn decode_for_test(package: &[u8], ts: u64) -> Result<Decoded> {
    let (core_key, meta_key) = derive_keys(ts);
    let mut input = Cursor::new(package);

    let mut header = [0u8; 10];
    input.read_exact(&mut header)?;
    assert_eq!(&header, HEADER);

    let mut key_frame = read_frame(&mut input)?;
    key_frame.iter_mut().for_each(|byte| *byte ^= 100);
    let key_plain = aes_decrypt(&mut key_frame, &core_key)?;
    if !key_plain.starts_with(KEY_PREFIX) {
        bail!("bad key");
    }
    let audio_key = key_plain[KEY_PREFIX.len()..].to_vec();

    let mut comment = read_frame(&mut input)?;
    comment.iter_mut().for_each(|byte| *byte ^= 99);
    if !comment.starts_with(COMMENT_PREFIX) {
        bail!("bad comment");
    }
    let mut meta_block = base64.decode(&comment[COMMENT_PREFIX.len()..])?;
    let meta_plain = aes_decrypt(&mut meta_block, &meta_key)?;
    if !meta_plain.starts_with(META_PREFIX) {
        bail!("bad meta");
    }
    let meta = meta_plain[META_PREFIX.len()..].to_vec();

    skip(&mut input, 5)?;
    let offset = read_len(&mut input)?;
    let image = read_frame(&mut input)?;
    if offset > image.len() {
        skip(&mut input, offset - image.len())?;
    }

    let mut audio = Vec::new();
    input.read_to_end(&mut audio)?;
    xor_audio(&mut audio, &audio_key);

    Ok(Decoded { audio, meta, image })
}

fn aes_decrypt<'a>(data: &'a mut [u8], key: &[u8; 16]) -> Result<&'a [u8]> {
    Aes128EcbDec::new(key.into())
        .decrypt_padded_mut::<Pkcs7>(data)
        .map_err(anyhow::Error::msg)
}

fn read_frame(input: &mut Cursor<&[u8]>) -> Result<Vec<u8>> {
    let len = read_len(input)?;
    let mut data = vec![0u8; len];
    input.read_exact(&mut data)?;
    Ok(data)
}

fn read_len(input: &mut Cursor<&[u8]>) -> Result<usize> {
    let mut buf = [0u8; 4];
    input.read_exact(&mut buf)?;
    Ok(u32::from_le_bytes(buf) as usize)
}

fn skip(input: &mut Cursor<&[u8]>, len: usize) -> Result<()> {
    let mut buf = vec![0u8; len];
    input.read_exact(&mut buf)?;
    Ok(())
}

fn valid_test_timestamp() -> u64 {
    TIME_BUCKET_MIN * BUCKET_SCALE + 4_242
}

fn build_test_flac(tags: &[(&str, &str)], picture: Option<&[u8]>, audio_body: &[u8]) -> Vec<u8> {
    let mut flac = Vec::from(&b"fLaC"[..]);
    append_flac_block(&mut flac, false, 0, &[0u8; 34]);
    append_flac_block(
        &mut flac,
        picture.is_none(),
        4,
        &build_vorbis_comment_block(tags),
    );
    if let Some(picture) = picture {
        append_flac_block(&mut flac, true, 6, &build_picture_block(picture));
    }
    flac.extend_from_slice(audio_body);
    flac
}

fn append_flac_block(out: &mut Vec<u8>, is_last: bool, block_type: u8, payload: &[u8]) {
    out.push(if is_last {
        0x80 | block_type
    } else {
        block_type
    });
    let len = payload.len() as u32;
    out.push(((len >> 16) & 0xff) as u8);
    out.push(((len >> 8) & 0xff) as u8);
    out.push((len & 0xff) as u8);
    out.extend_from_slice(payload);
}

fn build_vorbis_comment_block(tags: &[(&str, &str)]) -> Vec<u8> {
    let vendor = b"miniL-test";
    let mut payload = Vec::new();
    payload.extend_from_slice(&(vendor.len() as u32).to_le_bytes());
    payload.extend_from_slice(vendor);
    payload.extend_from_slice(&(tags.len() as u32).to_le_bytes());
    for (key, value) in tags {
        let entry = format!("{key}={value}");
        payload.extend_from_slice(&(entry.len() as u32).to_le_bytes());
        payload.extend_from_slice(entry.as_bytes());
    }
    payload
}

fn build_picture_block(data: &[u8]) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend_from_slice(&3u32.to_be_bytes());
    payload.extend_from_slice(&9u32.to_be_bytes());
    payload.extend_from_slice(b"image/png");
    payload.extend_from_slice(&11u32.to_be_bytes());
    payload.extend_from_slice(b"front cover");
    payload.extend_from_slice(&0u32.to_be_bytes());
    payload.extend_from_slice(&0u32.to_be_bytes());
    payload.extend_from_slice(&0u32.to_be_bytes());
    payload.extend_from_slice(&0u32.to_be_bytes());
    payload.extend_from_slice(&(data.len() as u32).to_be_bytes());
    payload.extend_from_slice(data);
    payload
}
