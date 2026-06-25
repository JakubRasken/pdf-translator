$ErrorActionPreference = "Stop"

$pythonPath = "C:\Users\jakub\Documents\AI\pdf_translator_pipeline\.venv\Scripts\python.exe"
$cliScript = "C:\Users\jakub\Documents\AI\pdf_translator_pipeline\cli.py"

$sourceDir = "C:\Users\jakub\Downloads\VIVAX_prelozit\SERVICE MANUAL"
$targetDir = "C:\Users\jakub\Downloads\VIVAX_prelozit\SERVICE MANUAL\translated"

if (!(Test-Path $targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

$pdfs = Get-ChildItem -Path $sourceDir -Filter "*.pdf" -File

foreach ($pdf in $pdfs) {
    $sourceFile = $pdf.FullName
    $targetFile = Join-Path $targetDir ($pdf.BaseName + "_translated.pdf")
    
    if (Test-Path $targetFile) {
        Write-Host "Skipping $($pdf.Name), already translated." -ForegroundColor Yellow
        continue
    }

    Write-Host "==========================================================="
    Write-Host "Starting translation for: $($pdf.Name)"
    Write-Host "Target: $targetFile"
    Write-Host "==========================================================="
    
    $env:PYTHONPATH="C:\Users\jakub\Documents\AI"
    
    # We use Google as engine as configured in the project
    & $pythonPath $cliScript $sourceFile $targetFile --target-lang cs --engine google
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Translation failed for $($pdf.Name) with exit code $LASTEXITCODE" -ForegroundColor Red
    } else {
        Write-Host "SUCCESS: Translated $($pdf.Name)" -ForegroundColor Green
    }
    Write-Host ""
}

Write-Host "All translations finished!"
