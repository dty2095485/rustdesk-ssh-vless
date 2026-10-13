using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Reflection;
using System.Security.Principal;
using System.Windows.Forms;

class Program
{
    static void Main()
    {
        // Do not reuse a fixed extraction directory. A running RustDesk
        // instance can still have Flutter plugin DLLs open there, which makes
        // an upgrade fail before RustDesk gets a chance to install itself.
        string dir = Path.Combine(
            Path.GetTempPath(),
            "RustDesk-VLESS-Setup",
            Guid.NewGuid().ToString("N"));
        try
        {
            if (!IsAdmin())
            {
                var psi = new ProcessStartInfo();
                psi.FileName = Process.GetCurrentProcess().MainModule.FileName;
                psi.UseShellExecute = true;
                psi.Verb = "runas";
                Process.Start(psi);
                return;
            }

            Directory.CreateDirectory(dir);
            var asm = Assembly.GetExecutingAssembly();
            using (var s = asm.GetManifestResourceStream("payload.zip"))
            using (var zip = new ZipArchive(s, ZipArchiveMode.Read))
            {
                foreach (var entry in zip.Entries)
                {
                    string dest = Path.Combine(dir, entry.FullName.Replace('/', '\\'));
                    if (string.IsNullOrEmpty(entry.Name))
                    {
                        Directory.CreateDirectory(dest);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(dest));
                    using (var es = entry.Open())
                    using (var fs = File.Create(dest))
                    {
                        es.CopyTo(fs);
                    }
                }
            }
            string exe = Path.Combine(dir, "rustdesk.exe");
            if (!File.Exists(exe))
                throw new FileNotFoundException("The embedded RustDesk program is missing.", exe);

            Process.Start(new ProcessStartInfo(exe, "--install") {
                UseShellExecute = true,
                WorkingDirectory = dir,
            });
        }
        catch (Exception e)
        {
            string log = Path.Combine(Path.GetTempPath(), "rustdesk-setup-error.log");
            try { File.WriteAllText(log, e.ToString()); } catch { }
            MessageBox.Show(
                "Installation could not start. Details were saved to:\n" + log,
                "RustDesk VLESS Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    static bool IsAdmin()
    {
        var id = WindowsIdentity.GetCurrent();
        var p = new WindowsPrincipal(id);
        return p.IsInRole(WindowsBuiltInRole.Administrator);
    }
}
