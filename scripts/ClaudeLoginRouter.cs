// Dedicated Win32 application identity; only forwards to the owned guarded shim.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
[assembly: AssemblyTitle("Claude Login Router")]
[assembly: AssemblyDescription("Explicit named-profile Claude login router")]
[assembly: AssemblyProduct("Claude Login Router")]
[assembly: AssemblyVersion("1.0.0.0")]
class ClaudeLoginRouter {
 static string Quote(string value) {
  StringBuilder b=new StringBuilder("\""); int slashes=0;
  foreach(char c in value) {
   if(c=='\\') {slashes++;continue;}
   if(c=='"') b.Append('\\',slashes*2+1).Append('"');
   else b.Append('\\',slashes).Append(c);
   slashes=0;
  }
  return b.Append('\\',slashes*2).Append('"').ToString();
 }
 [STAThread] static int Main(string[] args) {
  if(args.Length!=1 || args[0].Length>16384 ||
     !args[0].StartsWith("claude://",StringComparison.OrdinalIgnoreCase) ||
     args[0].IndexOfAny(new char[]{'\r','\n','\0'})>=0) return 2;
  string shim=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"ClaudeOpenShim.ps1");
  if(!File.Exists(shim)) return 2;
  string ps=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell\\v1.0\\powershell.exe");
  try {
   ProcessStartInfo p=new ProcessStartInfo(ps,"-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "+Quote(shim)+" -Url "+Quote(args[0]));
   p.UseShellExecute=false;p.CreateNoWindow=true;p.WindowStyle=ProcessWindowStyle.Hidden;
   using(Process child=Process.Start(p)) {child.WaitForExit();return child.ExitCode;}
  } catch {return 2;} // No URL, args or raw errors logged.
 }
}
