# Screenshot -> OCR analysis pipeline (Windows OCR, no vision model needed).
param(
    [string]$ImagePath = 'D:\chatgpt\vps-deploy\screen_now.png',
    [switch]$CaptureFirst
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) {
    $m = $asTaskGeneric.MakeGenericMethod($t)
    $task = $m.Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
if ($CaptureFirst) {
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Windows.Forms
    $b = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height)
    $g = [System.Drawing.Graphics]::FromImage($b)
    $g.CopyFromScreen(0,0,0,0,$b.Size)
    $b.Save($ImagePath)
    $g.Dispose(); $b.Dispose()
}
$uri = [Uri]("file:///" + ($ImagePath -replace '\\','/'))
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.DataWriter,Windows.Storage.Streams,ContentType=WindowsRuntime]
$stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
$dw = [Windows.Storage.Streams.DataWriter]::new($stream)
$dw.WriteBytes([IO.File]::ReadAllBytes($ImagePath))
$null = Await ($dw.StoreAsync()) ([uint32])
$null = Await ($dw.FlushAsync()) ([bool])
$stream.Seek(0)
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync([Windows.Storage.Streams.IRandomAccessStream]$stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hans')) }
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) }
Write-Output "OCR language: $($engine.RecognizerLanguage.LanguageTag)"
$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
Write-Output '--- OCR TEXT ---'
Write-Output $res.Text
