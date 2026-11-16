# Machine-only transport. Never write request headers, credentials or raw errors.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
# Windows PowerShell 5.1 on older/hardened systems may not negotiate TLS 1.2+ by default.
try {
    $protocols = [Net.SecurityProtocolType]::Tls12
    if ([Enum]::GetNames([Net.SecurityProtocolType]) -contains 'Tls13') { $protocols = $protocols -bor [Net.SecurityProtocolType]::Tls13 }
    [Net.ServicePointManager]::SecurityProtocol = $protocols
} catch {}
# Classify a failure without ever emitting the raw message (may contain URL details).
# Windows error messages are localized, so only exception types and WebExceptionStatus names are inspected.
function Get-ErrorKind($ex) {
    $text = ''
    $cursor = $ex
    while ($cursor) {
        $text += ' ' + $cursor.GetType().FullName
        if ($cursor -is [System.Net.WebException]) { $text += ' ' + $cursor.Status.ToString() }
        $cursor = $cursor.InnerException
    }
    if ($text -match 'SendFailure|SecureChannelFailure|TrustFailure|AuthenticationException|Win32Exception|CryptographicException|CertificateProblem') { return 'ssl' }
    if ($text -match 'Timeout|TaskCanceled|OperationCanceled') { return 'timeout' }
    if ($text -match 'NameResolutionFailure|ConnectFailure|ProxyNameResolutionFailure|SocketException|HttpRequestException') { return 'connect' }
    return 'other'
}
try {
    $inputData = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $headers = @{}
    foreach ($property in $inputData.headers.PSObject.Properties) { $headers[$property.Name] = [string]$property.Value }
    $params = @{
        Uri = [string]$inputData.url
        Headers = $headers
        TimeoutSec = [int]$inputData.timeout
        MaximumRedirection = 0
        UseBasicParsing = $true
    }
    if ($null -ne $inputData.body) {
        $params.Method = 'Post'
        $params.Body = [Convert]::FromBase64String([string]$inputData.body)
        if ($headers.ContainsKey('Content-Type')) {
            $params.ContentType = $headers['Content-Type']
            $headers.Remove('Content-Type')
        }
    } else { $params.Method = 'Get' }
    $response = Invoke-WebRequest @params
    $bytes = $response.RawContentStream.ToArray()
    if ($bytes.Length -gt 83886080) { exit 1 }
    $responseHeaders = @{}
    foreach ($key in $response.Headers.Keys) { $responseHeaders[$key] = [string]($response.Headers[$key] -join ', ') }
    $output = @{status=[int]$response.StatusCode; headers=$responseHeaders; body=[Convert]::ToBase64String($bytes)}
    [Console]::Out.Write(($output | ConvertTo-Json -Depth 5 -Compress))
} catch {
    $status = 0
    $kind = ''
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode } else { $kind = Get-ErrorKind $_.Exception }
    [Console]::Out.Write((@{status=$status; error=$kind; headers=@{}; body=''} | ConvertTo-Json -Compress))
}
