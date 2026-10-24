<#
.SYNOPSIS
    Initialise this folder as a git repository and publish it to GitHub.

.DESCRIPTION
    One command to get https://github.com/<owner>/ninja-defenders-free created
    and pushed.  Uses the GitHub CLI when it is installed and authenticated;
    otherwise it prepares the commit and prints the commands you still need.

.EXAMPLE
    ./publish.ps1

.EXAMPLE
    ./publish.ps1 -Owner iamafreeride -Private -Description "Daily free Ruby Cat Stone claimer"
#>
[CmdletBinding()]
param(
    [string]$Owner,

    [string]$Repo = "ninja-defenders-free",

    [string]$Description = "Claim the daily free Ruby Cat Stone on the Ninja Defenders web shop",

    [switch]$Private
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed" }
}

if (-not $Owner) {
    $Owner = (& git config user.name).Trim()
}
if (-not $Owner) {
    throw "No GitHub owner: pass -Owner <your-github-username>."
}

$name = (& git config user.name).Trim()
$email = (& git config user.email).Trim()
if (-not $name -or -not $email) {
    throw "Git identity missing. Run: git config --global user.name ""Your Name""; git config --global user.email ""you@example.com"""
}

Write-Host "==> Preparing repository" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath ".git")) {
    Invoke-Git init --initial-branch=main
}

Invoke-Git add -A
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Nothing new to commit." -ForegroundColor Yellow
}
else {
    Invoke-Git commit -m "Initial commit: automated daily Ruby Cat Stone claimer"
}

$visibility = if ($Private) { "--private" } else { "--public" }
$hasGh = Get-Command gh -ErrorAction SilentlyContinue

if ($hasGh) {
    & gh auth status *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "==> Creating github.com/$Owner/$Repo and pushing" -ForegroundColor Cyan
        & git remote remove origin 2>$null
        & gh repo create "$Owner/$Repo" $visibility --description $Description --source . --remote origin --push
        if ($LASTEXITCODE -ne 0) { throw "gh repo create failed" }
        Write-Host "==> Done: https://github.com/$Owner/$Repo" -ForegroundColor Green
        exit 0
    }
    Write-Host "gh is installed but not authenticated (run: gh auth login)." -ForegroundColor Yellow
}
else {
    Write-Host "GitHub CLI (gh) not found." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "The commit is ready but was NOT pushed. Two ways to finish:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  A) With gh (recommended)"
Write-Host "     gh auth login"
Write-Host "     gh repo create $Owner/$Repo $visibility --source . --remote origin --push"
Write-Host ""
Write-Host "  B) Create the repository by hand at https://github.com/new (name: $Repo, no README), then:"
Write-Host "     git remote add origin https://github.com/$Owner/$Repo.git"
Write-Host "     git push -u origin main"
