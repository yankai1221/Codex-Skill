# Machine-only transport. Never write request headers, credentials or raw errors.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
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
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    [Console]::Out.Write((@{status=$status; headers=@{}; body=''} | ConvertTo-Json -Compress))
}
