param (
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = Split-Path -Parent $ScriptDir
$ModelsDir = Join-Path $ProjectDir "models"

# Configuration des modèles
$Models = @(
    @{
        Name = "Qwen 3.5 4B MTP (Coder, Router)"
        Folder = "qwen35-4b-mtp"
        File = "Qwen3.5-4B-Q4_K_M.gguf"
        Url = "https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"
    },
    @{
        Name = "Qwen 3.5 4B MTP - Vision Projector (mmproj)"
        Folder = "qwen35-4b-mtp"
        File = "mmproj-F16.gguf"
        Url = "https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF/resolve/main/mmproj-F16.gguf"
    },
    @{
        Name = "Ornith 1.0 9B (Architect, Tester, Judge, Security)"
        Folder = "ornith-1.0"
        File = "Ornith-1.0-9B-MTP-Q4_K_M.gguf"
        Url = "https://huggingface.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF/resolve/main/Ornith-1.0-9B-MTP-Q4_K_M.gguf"
    }
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " Téléchargement des modèles GGUF locaux" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Dossier cible : $ModelsDir`n"

foreach ($Model in $Models) {
    $TargetFolder = Join-Path $ModelsDir $Model.Folder
    $TargetFile = Join-Path $TargetFolder $Model.File
    
    # Création du répertoire si nécessaire
    if (!(Test-Path $TargetFolder)) {
        New-Item -ItemType Directory -Force -Path $TargetFolder | Out-Null
        Write-Host "Création du dossier : $TargetFolder" -ForegroundColor DarkGray
    }

    # Téléchargement
    if ((Test-Path $TargetFile) -and (-not $Force)) {
        Write-Host "[SKIPPED] Le fichier $($Model.File) existe déjà." -ForegroundColor Yellow
        Write-Host "          (Utilisez le paramètre -Force pour forcer le retéléchargement)`n"
    } else {
        Write-Host "[DOWNLOADING] $($Model.Name)..." -ForegroundColor Magenta
        Write-Host "              URL: $($Model.Url)" -ForegroundColor DarkGray
        Write-Host "              Vers: $TargetFile" -ForegroundColor DarkGray
        
        try {
            Invoke-WebRequest -Uri $Model.Url -OutFile $TargetFile -UseBasicParsing
            Write-Host "[SUCCESS] $($Model.File) téléchargé avec succès !`n" -ForegroundColor Green
        } catch {
            Write-Host "[ERROR] Échec du téléchargement de $($Model.File): $_" -ForegroundColor Red
            Write-Host ""
        }
    }
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Tous les téléchargements sont terminés." -ForegroundColor Cyan
Write-Host "Assurez-vous que votre fichier .env pointe bien vers :"
Write-Host "FAST_MODEL = `$ModelsDir\qwen35-4b\Qwen3.5-4B-Q4_K_M.gguf"
Write-Host "REASONING_MODEL = $ModelsDir\ornith-1.0\Ornith-1.0-9B-MTP-Q4_K_M.gguf"
Write-Host "=========================================" -ForegroundColor Cyan
