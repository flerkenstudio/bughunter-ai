# Configure GitHub labels and topics for an existing repository.
# Usage: .\scripts\github-setup.ps1 -Repo OWNER/bughunter-ai
param(
    [Parameter(Mandatory = $true)]
    [string]$Repo
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required: https://cli.github.com/"
}

gh auth status | Out-Null

$labels = @(
    @{ Name = "bug"; Color = "d73a4a"; Description = "Confirmed defect with reproduced evidence" },
    @{ Name = "enhancement"; Color = "a2eeef"; Description = "New capability or improvement" },
    @{ Name = "documentation"; Color = "0075ca"; Description = "README, docs and walkthroughs" },
    @{ Name = "security"; Color = "b60205"; Description = "Target policy, isolation, secrets" },
    @{ Name = "testing"; Color = "1d76db"; Description = "Runner, suites, evidence integrity" },
    @{ Name = "p0"; Color = "5319e7"; Description = "Hackathon P0: must work" },
    @{ Name = "p1"; Color = "0e8a16"; Description = "Hackathon P1: differentiator" },
    @{ Name = "p2"; Color = "fbca04"; Description = "Hackathon P2: optional" },
    @{ Name = "good first issue"; Color = "7057ff"; Description = "Small, well-scoped work" },
    @{ Name = "hackathon"; Color = "ff8c00"; Description = "OpenFire event work" }
)

foreach ($label in $labels) {
    gh label create $label.Name --repo $Repo --color $label.Color --description $label.Description --force
    Write-Host "label: $($label.Name)"
}

$topics = @(
    "ai-testing", "autonomous-agents", "qa-automation", "browser-testing", "playwright",
    "fastapi", "react", "typescript", "sqlite", "bug-reproduction", "patch-verification",
    "hackathon", "openfire", "software-testing", "test-automation"
)

gh repo edit $Repo --add-topic ($topics -join ",")
Write-Host "topics: $($topics -join ', ')"

Write-Host ""
Write-Host "Next: gh release create v0.1.0 --title 'v0.1.0 - failure to verified fix' --notes-file CHANGELOG.md"
