param(
    [ValidateSet('claude', 'copilot', 'both')]
    [string]$Client = 'claude'
)

$ErrorActionPreference = 'Stop'
$windowsHost = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$linkType = if ($windowsHost) { 'Junction' } else { 'SymbolicLink' }
$comparison = if ($windowsHost) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$targets = @()
if ($Client -in @('claude', 'both')) {
    $targets += if ($env:CLAUDE_SKILLS_DIR) { $env:CLAUDE_SKILLS_DIR } else { Join-Path $HOME '.claude\skills' }
}
if ($Client -in @('copilot', 'both')) {
    $copilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $HOME '.copilot' }
    $targets += if ($env:COPILOT_SKILLS_DIR) { $env:COPILOT_SKILLS_DIR } else { Join-Path $copilotHome 'skills' }
}

foreach ($target in $targets) {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    foreach ($skill in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'skills') -Directory) {
        if (-not (Test-Path -LiteralPath (Join-Path $skill.FullName 'SKILL.md') -PathType Leaf)) { continue }
        $destination = Join-Path $target $skill.Name
        $existing = Get-Item -LiteralPath $destination -Force -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            $linkedTarget = @($existing.Target)[0]
            if ($existing.LinkType -in @('Junction', 'SymbolicLink') -and $linkedTarget) {
                if (-not [IO.Path]::IsPathRooted($linkedTarget)) {
                    $linkedTarget = Join-Path $target $linkedTarget
                }
                if ([string]::Equals([IO.Path]::GetFullPath($linkedTarget), $skill.FullName, $comparison)) {
                    Write-Output "ok      $($skill.Name) (already linked)"
                    continue
                }
            }
            Write-Warning "skip    $($skill.Name): $destination already exists"
            continue
        }
        New-Item -ItemType $linkType -Path $destination -Target $skill.FullName | Out-Null
        Write-Output "linked  $($skill.Name) -> $($skill.FullName)"
    }
}
