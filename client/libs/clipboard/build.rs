#[cfg(target_os = "windows")]
fn build_c_impl() {
    let mut build = cc::Build::new();

    build.file("src/windows/wf_cliprdr.c");

    {
        build.flag_if_supported("-Wno-c++0x-extensions");
        build.flag_if_supported("-Wno-return-type-c-linkage");
        build.flag_if_supported("-Wno-invalid-offsetof");
        build.flag_if_supported("-Wno-unused-parameter");

        if build.get_compiler().is_like_msvc() {
            build.define("WIN32", "");
            // build.define("_AMD64_", "");
        // MSVC 14.44 fails with D8050 (cannot execute c1.dll) when -Z7 has to
// store the compile command line in CodeView and the build path is long;
// keep C debug info opt-in for local and CI builds.
        if std::env::var("RUSTDESK_C_DEBUGINFO").is_ok() {
            build.flag("-Z7");
        }
            build.flag("-GR-");
            // build.flag("-std:c++11");
        } else {
            build.flag("-fPIC");
            // build.flag("-std=c++11");
            // build.flag("-include");
            // build.flag(&confdefs_path.to_string_lossy());
        }

        build.compile("mycliprdr");
    }

    println!("cargo:rerun-if-changed=src/windows/wf_cliprdr.c");
}

fn main() {
    #[cfg(target_os = "windows")]
    build_c_impl();
}
