use std::{
    env, fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

const WINDOW_BUCKET_RADIUS: u64 = 20_000;

fn main() {
    let bucket = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock is before unix epoch")
        .as_secs()
        / 10_000;
    let bucket_min = bucket.saturating_sub(WINDOW_BUCKET_RADIUS);
    let bucket_max = bucket + WINDOW_BUCKET_RADIUS;

    let output =
        PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR missing")).join("build_consts.rs");
    fs::write(
        output,
        format!(
            "static TIME_BUCKET_MIN: u64 = {bucket_min};\nstatic TIME_BUCKET_MAX: u64 = {bucket_max};\n"
        ),
    )
    .expect("write build consts");

    println!("cargo:rerun-if-changed=build.rs");
}
