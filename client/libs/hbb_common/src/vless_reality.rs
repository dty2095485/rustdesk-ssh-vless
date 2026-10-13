use crate::{
    bail,
    config::{Config, Socks5Server, VlessServer},
    sha2::{Digest, Sha256},
    tcp::FramedStream,
    ResultType,
};
use serde_json::{json, Value};
use std::{
    convert::TryFrom,
    fs,
    path::PathBuf,
    process::{Child, Command, Stdio},
    time::Duration,
};
use tokio::{net::TcpListener, sync::Mutex, time::sleep};

const OPTION_PUBLIC_KEY: &str = "vless-reality-public-key";
const OPTION_SHORT_ID: &str = "vless-reality-short-id";
const OPTION_FINGERPRINT: &str = "vless-reality-fingerprint";
const OPTION_FLOW: &str = "vless-reality-flow";

crate::lazy_static::lazy_static! {
    static ref SIDECAR: Mutex<Option<RealitySidecar>> = Mutex::new(None);
}

struct RealitySettings {
    endpoint: String,
    port: u16,
    uuid: String,
    server_name: String,
    public_key: String,
    short_id: String,
    fingerprint: String,
    flow: String,
}

struct RealitySidecar {
    child: Child,
    local_port: u16,
    signature: String,
    #[cfg(target_os = "windows")]
    job: Option<WindowsJob>,
}

impl Drop for RealitySidecar {
    fn drop(&mut self) {
        #[cfg(target_os = "windows")]
        if let Some(job) = self.job.take() {
            drop(job);
            return;
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl RealitySettings {
    fn from_config(config: &VlessServer) -> ResultType<Self> {
        let port = u16::try_from(config.port)
            .map_err(|_| anyhow::anyhow!("VLESS Reality port is invalid"))?;
        if config.server.is_empty() || config.uuid.is_empty() || config.server_name.is_empty() {
            bail!("VLESS Reality server, UUID and SNI are required");
        }
        uuid::Uuid::parse_str(&config.uuid)
            .map_err(|err| anyhow::anyhow!("VLESS Reality UUID is invalid: {err}"))?;
        let public_key = Config::get_option(OPTION_PUBLIC_KEY);
        let short_id = Config::get_option(OPTION_SHORT_ID);
        if public_key.is_empty() || short_id.is_empty() {
            bail!("VLESS Reality public key and short ID are required");
        }
        let fingerprint = match Config::get_option(OPTION_FINGERPRINT).as_str() {
            "" => "chrome".to_owned(),
            value => value.to_owned(),
        };
        let flow = match Config::get_option(OPTION_FLOW).as_str() {
            "" => "xtls-rprx-vision".to_owned(),
            "none" => String::new(),
            value => value.to_owned(),
        };
        Ok(Self {
            endpoint: config.server.clone(),
            port,
            uuid: config.uuid.clone(),
            server_name: config.server_name.clone(),
            public_key,
            short_id,
            fingerprint,
            flow,
        })
    }

    fn signature(&self) -> String {
        let source = format!(
            "{}:{}:{}:{}:{}:{}:{}:{}",
            self.endpoint,
            self.port,
            self.uuid,
            self.server_name,
            self.public_key,
            self.short_id,
            self.fingerprint,
            self.flow
        );
        format!("{:x}", Sha256::digest(source.as_bytes()))
    }
}

pub async fn connect(
    target: &str,
    config: &VlessServer,
    ms_timeout: u64,
) -> ResultType<FramedStream> {
    let settings = RealitySettings::from_config(config)?;
    let local_port = ensure_sidecar(&settings, ms_timeout).await?;
    let target = restricted_target(target)?;
    let proxy = Socks5Server {
        proxy: format!("127.0.0.1:{local_port}"),
        username: String::new(),
        password: String::new(),
    };
    FramedStream::connect(target.as_str(), None, &proxy, ms_timeout).await
}

fn restricted_target(target: &str) -> ResultType<String> {
    let port = if let Ok(address) = target.parse::<std::net::SocketAddr>() {
        address.port()
    } else {
        target
            .rsplit_once(':')
            .ok_or_else(|| anyhow::anyhow!("VLESS Reality target must include a port"))?
            .1
            .parse::<u16>()?
    };
    // The REALITY credential is checked by Xray before this destination is
    // opened. Route it to the same authenticated-only loopback listeners used
    // by hbvless/hbssh, never to the public RustDesk listeners.
    let port = match port {
        21115 => 22115,
        21116 => 22116,
        21117 | 443 | 8443 => 22117,
        _ => bail!("VLESS Reality destination port is not permitted"),
    };
    Ok(format!("127.0.0.1:{port}"))
}

async fn ensure_sidecar(settings: &RealitySettings, ms_timeout: u64) -> ResultType<u16> {
    let signature = settings.signature();
    let mut sidecar = SIDECAR.lock().await;
    if let Some(current) = sidecar.as_mut() {
        if current.signature == signature && current.child.try_wait()?.is_none() {
            return Ok(current.local_port);
        }
    }
    sidecar.take();

    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let local_port = listener.local_addr()?.port();
    drop(listener);

    let executable = sidecar_executable()?;
    let config_path = write_sidecar_config(settings, local_port)?;
    let mut command = Command::new(&executable);
    command
        .arg("run")
        .arg("-c")
        .arg(&config_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if let Some(parent) = executable.parent() {
        command.current_dir(parent);
    }
    #[cfg(target_os = "android")]
    {
        use std::os::unix::{fs::OpenOptionsExt, process::CommandExt};
        let log_path = config_path.with_extension("log");
        let log = fs::OpenOptions::new().create(true).append(true).mode(0o600).open(log_path)?;
        command.stderr(Stdio::from(log));
        // Do not leave the tunnel running after Android kills the app process.
        unsafe {
            command.pre_exec(|| {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|err| {
        anyhow::anyhow!(
            "Failed to start the bundled Xray Reality core at {}: {err}",
            executable.display()
        )
    })?;
    #[cfg(target_os = "windows")]
    let job = match WindowsJob::attach(&child) {
        Ok(job) => Some(job),
        Err(err) => {
            log::warn!("Could not attach Xray to the RustDesk process job: {err}");
            None
        }
    };

    let wait_limit = Duration::from_millis(ms_timeout.clamp(1_000, 10_000));
    let started = std::time::Instant::now();
    loop {
        if tokio::net::TcpStream::connect(("127.0.0.1", local_port))
            .await
            .is_ok()
        {
            break;
        }
        if let Some(status) = child.try_wait()? {
            bail!("Bundled Xray Reality core exited during startup: {status}");
        }
        if started.elapsed() >= wait_limit {
            let _ = child.kill();
            let _ = child.wait();
            bail!("Timed out starting the bundled Xray Reality core");
        }
        sleep(Duration::from_millis(50)).await;
    }

    *sidecar = Some(RealitySidecar {
        child,
        local_port,
        signature,
        #[cfg(target_os = "windows")]
        job,
    });
    Ok(local_port)
}

fn sidecar_executable() -> ResultType<PathBuf> {
    #[cfg(target_os = "android")]
    {
        let directory = std::env::var("RUSTDESK_ANDROID_NATIVE_LIB_DIR")
            .map_err(|_| anyhow::anyhow!("Android native library directory is unavailable"))?;
        let executable = PathBuf::from(directory).join("libxray.so");
        if !executable.is_absolute() || !executable.is_file() {
            bail!("Bundled Android Xray Reality core is missing");
        }
        return Ok(executable);
    }
    #[cfg(not(target_os = "android"))]
    {
    let current = std::env::current_exe()?;
    let parent = current
        .parent()
        .ok_or_else(|| anyhow::anyhow!("RustDesk executable directory is unavailable"))?;
    let name = if cfg!(target_os = "windows") {
        "xray.exe"
    } else {
        "xray"
    };
    let executable = parent.join(name);
    if !executable.is_file() {
        bail!(
            "Bundled Xray Reality core is missing: {}",
            executable.display()
        );
    }
    Ok(executable)
    }
}

fn write_sidecar_config(settings: &RealitySettings, local_port: u16) -> ResultType<PathBuf> {
    let config = build_sidecar_config(settings, local_port);
    #[cfg(target_os = "android")]
    let temporary = PathBuf::from(std::env::var("RUSTDESK_ANDROID_CACHE_DIR")
        .map_err(|_| anyhow::anyhow!("Android private cache directory is unavailable"))?);
    #[cfg(not(target_os = "android"))]
    let temporary = std::env::temp_dir();
    let directory = temporary.join(format!(
        "rustdesk-reality-{}",
        std::process::id()
    ));
    fs::create_dir_all(&directory)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o700))?;
    }
    let path = directory.join("config.json");
    fs::write(&path, serde_json::to_vec_pretty(&config)?)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(path)
}

fn build_sidecar_config(settings: &RealitySettings, local_port: u16) -> Value {
    json!({
        "log": { "loglevel": "warning" },
        "inbounds": [{
            "tag": "rustdesk-local",
            "listen": "127.0.0.1",
            "port": local_port,
            "protocol": "socks",
            "settings": { "auth": "noauth", "udp": false },
            "sniffing": { "enabled": false }
        }],
        "outbounds": [{
            "tag": "rustdesk-reality",
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": settings.endpoint,
                    "port": settings.port,
                    "users": [{
                        "id": settings.uuid,
                        "encryption": "none",
                        "flow": settings.flow
                    }]
                }]
            },
            "streamSettings": {
                "network": "raw",
                "security": "reality",
                "realitySettings": {
                    "show": false,
                    "fingerprint": settings.fingerprint,
                    "serverName": settings.server_name,
                    "password": settings.public_key,
                    "shortId": settings.short_id,
                    "spiderX": "/"
                }
            }
        }],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{
                "type": "field",
                "inboundTag": ["rustdesk-local"],
                "outboundTag": "rustdesk-reality"
            }]
        }
    })
}

#[cfg(target_os = "windows")]
struct WindowsJob(winapi::um::winnt::HANDLE);

#[cfg(target_os = "windows")]
unsafe impl Send for WindowsJob {}

#[cfg(target_os = "windows")]
impl WindowsJob {
    fn attach(child: &Child) -> ResultType<Self> {
        use std::{mem::zeroed, os::windows::io::AsRawHandle};
        use winapi::{
            shared::minwindef::FALSE,
            um::{
                jobapi2::{AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject},
                winnt::{
                    JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
                    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                },
            },
        };
        unsafe {
            let job = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
            if job.is_null() {
                return Err(std::io::Error::last_os_error().into());
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            ) == FALSE
            {
                winapi::um::handleapi::CloseHandle(job);
                return Err(std::io::Error::last_os_error().into());
            }
            if AssignProcessToJobObject(job, child.as_raw_handle() as _) == FALSE {
                winapi::um::handleapi::CloseHandle(job);
                return Err(std::io::Error::last_os_error().into());
            }
            Ok(Self(job))
        }
    }
}

#[cfg(target_os = "windows")]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            winapi::um::handleapi::CloseHandle(self.0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{build_sidecar_config, restricted_target, RealitySettings};

    #[test]
    fn reality_targets_are_loopback_only() {
        assert_eq!(restricted_target("server.example:21116").unwrap(), "127.0.0.1:22116");
        assert_eq!(restricted_target("server.example:443").unwrap(), "127.0.0.1:22117");
        assert!(restricted_target("server.example:22").is_err());
    }

    #[test]
    fn reality_config_uses_current_xray_fields() {
        let settings = RealitySettings {
            endpoint: "rd.example.com".to_owned(),
            port: 443,
            uuid: "11111111-1111-4111-8111-111111111111".to_owned(),
            server_name: "rd.example.com".to_owned(),
            public_key: "public-key".to_owned(),
            short_id: "0123456789abcdef".to_owned(),
            fingerprint: "chrome".to_owned(),
            flow: String::new(),
        };
        let config = build_sidecar_config(&settings, 10808);
        let user = &config["outbounds"][0]["settings"]["vnext"][0]["users"][0];
        let reality = &config["outbounds"][0]["streamSettings"]["realitySettings"];
        assert_eq!(user["flow"], "");
        assert_eq!(reality["password"], "public-key");
        assert_eq!(reality["shortId"], "0123456789abcdef");
        assert_eq!(reality["serverName"], "rd.example.com");
    }
}
