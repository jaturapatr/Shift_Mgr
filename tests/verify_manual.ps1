# verify_manual.ps1
# Verifies the existence and structure of USER_MANUAL.md

$manualPath = "USER_MANUAL.md"
$requiredHeaders = @(
    "1. Introduction",
    "2. Quick Start Guide",
    "3. Setup & Requirements",
    "4. Interface Guide",
    "5. Constraint Management & Logic",
    "6. Maintenance & Safety",
    "7. Troubleshooting"
)

Write-Host "--- Verifying User Manual ---" -ForegroundColor Cyan

if (-not (Test-Path $manualPath)) {
    Write-Error "USER_MANUAL.md not found!"
    exit 1
}

$content = Get-Content $manualPath -Raw
$errors = 0

foreach ($header in $requiredHeaders) {
    if ($content -notmatch [regex]::Escape($header)) {
        Write-Host "[FAIL] Missing Section: $header" -ForegroundColor Red
        $errors++
    } else {
        Write-Host "[PASS] Found Section: $header" -ForegroundColor Green
    }
}

# Check for PowerShell snippets
if ($content -match "powershell") {
    Write-Host "[PASS] Contains PowerShell setup instructions" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Missing PowerShell setup instructions" -ForegroundColor Red
    $errors++
}

# Check for Quick Start depth
if ($content -match "Roster in 5 Minutes") {
    Write-Host "[PASS] Quick Start Guide identified" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Quick Start Guide content missing" -ForegroundColor Red
    $errors++
}

if ($errors -eq 0) {
    Write-Host "`nVerification Successful!" -ForegroundColor Green
} else {
    Write-Host "`nVerification Failed with $errors errors." -ForegroundColor Red
    exit 1
}
