<#
.SYNOPSIS
  Met à jour le build CUDA 13 pré-built de llama.cpp dans vendor/llamacpp-cuda13/.

.DESCRIPTION
  Télécharge la dernière release de llama.cpp (https://github.com/ggerganov/llama.cpp)
  pour Windows x64 + CUDA 13.x, l'extrait dans vendor/llamacpp-cuda13/ (gitignoré).

  Télécharge DEUX assets par release :
    1. llama-b<TAG>-bin-win-cuda-13.x-x64.zip   → binaires (llama-server.exe, ggml*.dll...)
    2. cudart-llama-bin-win-cuda-13.x-x64.zip    → DLLs runtime CUDA (cublasLt64_13.dll...)

  Le swap est atomique (backup .bak, extraction validée, then cleanup) : si le
  téléchargement ou l'extraction échoue en cours de route, l'ancien build est
  restauré intact.

  DÉCOUVERTE AUTOMATIQUE : llama_server.py détecte le GPU NVIDIA (via nvidia-smi) et
  choisit le dossier vendor dans cet ordre : llamacpp-cuda13 (préféré) → llamacpp-cuda
  (repli legacy CUDA 12) → PATH système (Vulkan/CPU fallback). Sur une machine sans
  GPU NVIDIA, les dossiers CUDA sont ignorés (sinon llama-server crash sur ggml-cuda.dll).

  ⚠️  NE PAS LANCER PENDANT UN RUN du graphe (agent_graph.py) — le binaire
  llama-server.exe est verrouillé par le process et ne peut pas être remplacé.
  Le script détecte un llama-server en cours d'exécution et refuse de continuer.

.PARAMETER Force
  Retélécharger même si la version locale correspond à la dernière release GitHub.

.PARAMETER KeepBackup
  Conserver le dossier .bak après une mise à jour réussie (par défaut supprimé).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\update_llamacpp.ps1
  powershell -ExecutionPolicy Bypass -File scripts\update_llamacpp.ps1 -Force
#>

param (
    [switch]$Force = $false,
    [switch]$KeepBackup = $false
)

$ErrorActionPreference = "Stop"

# --- Localisation (fonctionne quel que soit le cwd de l'appelant) ---
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = Split-Path -Parent $ScriptDir
$VendorDir  = Join-Path $ProjectDir "vendor"
$TargetDir  = Join-Path $VendorDir "llamacpp-cuda13"

$RepoApiUrl = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"

# --- En-tête ---
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Mise à jour de llama.cpp (build CUDA 13, Windows)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Dossier cible : $TargetDir`n"

# --- Garde anti-run : refuser si llama-server tourne ---
$running = Get-Process -Name "llama-server" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[ABORT] Un process 'llama-server' est en cours d'exécution ($($running.Count) instance(s))." -ForegroundColor Red
    Write-Host "        Le binaire est verrouillé et ne peut pas être remplacé." -ForegroundColor Red
    Write-Host "        Arrêtez d'abord le run du graphe (agent_graph.py), puis relancez ce script." -ForegroundColor Yellow
    exit 1
}

# --- Lecture de la version locale installée ---
# Source de vérité prioritaire : le fichier marqueur .llamacpp-version (écrit par ce
# script à chaque mise à jour réussie). Repli : on interroge directement le binaire
# (llama-server affiche "version: NNNNN (sha)" au démarrage — fiable, pas de drift).
$VersionFile = Join-Path $TargetDir ".llamacpp-version"
$LocalVersion = $null
if (Test-Path $VersionFile) {
    $LocalVersion = (Get-Content $VersionFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
}
# Repli : interroger le binaire si pas de marqueur (ex: dossier pré-existant sans
# marqueur, installé manuellement avant que ce script n'existe).
if (-not $LocalVersion) {
    $localServer = Join-Path $TargetDir "llama-server.exe"
    if (Test-Path $localServer) {
        Write-Host "[*] Pas de marqueur .llamacpp-version → interrogation du binaire..." -ForegroundColor DarkGray
        try {
            # llama-server --version renvoie "version: NNNNN (sha)" puis démarre un serveur.
            # On ne capture que la 1re ligne et on kill immédiatement. Timeout 10s de sécurité.
            $job = Start-Job -ScriptBlock { param($p) & $p --version 2>&1 | Select-Object -First 1 } -ArgumentList $localServer
            if (Wait-Job $job -Timeout 10) {
                $line = (Receive-Job $job | Select-Object -First 1)
                if ($line -match "version:\s*(\d+)") {
                    $LocalVersion = "b" + $matches[1]
                    Write-Host "[+] Version détectée depuis le binaire : $LocalVersion" -ForegroundColor DarkGray
                }
            }
            Remove-Job $job -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Host "[i] Impossible d'interroger le binaire pour la version : $_" -ForegroundColor DarkGray
        }
    }
}

# --- Interroger l'API GitHub pour la dernière release ---
Write-Host "[*] Interrogation de l'API GitHub (release la plus récente)..." -ForegroundColor DarkGray
$headers = @{ "User-Agent" = "graph-orchestrator-update-script" }
try {
    $release = Invoke-RestMethod -Uri $RepoApiUrl -Headers $headers -TimeoutSec 30
} catch {
    Write-Host "[ERROR] Impossible de joindre l'API GitHub : $_" -ForegroundColor Red
    Write-Host "        (Rate limit ? Pas de réseau ? Le script tourne trop souvent ?)" -ForegroundColor DarkGray
    exit 1
}

$LatestTag = $release.tag_name  # ex: "b10299"
Write-Host "[+] Dernière release GitHub : $LatestTag"

if ($LocalVersion -and ($LocalVersion -eq $LatestTag) -and -not $Force) {
    Write-Host "[SKIPPED] Vous êtes déjà à jour ($LocalVersion)." -ForegroundColor Green
    Write-Host "          (Utilisez -Force pour forcer la réinstallation.)`n"
    exit 0
}

if ($LocalVersion) {
    Write-Host "[*] Version locale actuelle : $LocalVersion → mise à jour vers $LatestTag`n" -ForegroundColor Yellow
} else {
    Write-Host "[*] Aucune version locale détectée → installation fraîche de $LatestTag`n" -ForegroundColor Yellow
}

# --- Sélection des assets CUDA 13 ---
# On matche le pattern "bin-win-cuda-13" (regex) pour rester insensible à la
# mineure (13.0, 13.3, 13.4...). Les assets cu12 ne doivent PAS matcher.
$binAsset    = $release.assets | Where-Object { $_.name -match "bin-win-cuda-13\.[0-9]+-x64\.zip$" } | Select-Object -First 1
$cudartAsset = $release.assets | Where-Object { $_.name -match "^cudart-.*bin-win-cuda-13\.[0-9]+-x64\.zip$" } | Select-Object -First 1

if (-not $binAsset) {
    Write-Host "[ERROR] Aucun asset binaire CUDA 13 trouvé dans la release $LatestTag." -ForegroundColor Red
    Write-Host "        Assets disponibles :" -ForegroundColor DarkGray
    $release.assets | ForEach-Object { Write-Host "          - $($_.name)" -ForegroundColor DarkGray }
    Write-Host "        (La release publie peut-être un autre naming CUDA ; vérifiez manuellement.)" -ForegroundColor Yellow
    exit 1
}

Write-Host "[+] Asset binaires  : $($binAsset.name)"
if ($cudartAsset) {
    Write-Host "[+] Asset CUDA runtime : $($cudartAsset.name)"
} else {
    Write-Host "[i] Pas d'asset cudart séparé pour cette release (DLLs runtime peut-être bundlées)." -ForegroundColor DarkGray
}

# --- Préparation : dossiers de travail temporaires ---
$TempDir = Join-Path $env:TEMP "llamacpp-update-$LatestTag-$(Get-Random)"
$ExtractDir = Join-Path $TempDir "extracted"
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

# Nettoyage du temp à la fin (réussite OU échec).
$cleanupTemp = {
    if (Test-Path $TempDir) {
        try { Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue } catch {}
    }
}

try {
    # --- Téléchargement ---
    $assetsToDownload = @($binAsset)
    if ($cudartAsset) { $assetsToDownload += $cudartAsset }

    foreach ($asset in $assetsToDownload) {
        $zipPath = Join-Path $TempDir $asset.name
        $sizeMB = [math]::Round($asset.size / 1MB, 1)
        Write-Host "[DOWNLOADING] $($asset.name) ($sizeMB MB)..." -ForegroundColor Magenta
        # UseBasicParsing + durée : Invoke-WebRequest affiche une barre de progression native.
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing -Headers $headers
        Write-Host "[EXTRACTING]  $($asset.name)..." -ForegroundColor DarkGray
        Expand-Archive -Path $zipPath -DestinationPath $ExtractDir -Force
    }

    # --- Validation : llama-server.exe doit être présent dans l'extraction ---
    $extractedServer = Get-ChildItem -Path $ExtractDir -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $extractedServer) {
        Write-Host "[ERROR] 'llama-server.exe' absent de l'archive extraite — build inattendu, abort." -ForegroundColor Red
        & $cleanupTemp
        exit 1
    }

    # Si les binaires sont dans un sous-dossier de l'extraction, on prend ce sous-dossier.
    $SourceDir = Split-Path -Parent $extractedServer.FullName
    Write-Host "[+] Source validée : $SourceDir" -ForegroundColor Green

    # --- Backup de l'ancien build (swap atomique) ---
    $BackupDir = "$TargetDir.bak"
    if (Test-Path $TargetDir) {
        if (Test-Path $BackupDir) { Remove-Item -Recurse -Force $BackupDir }
        Rename-Item -Path $TargetDir -NewName (Split-Path -Leaf $BackupDir)
        Write-Host "[+] Ancien build sauvegardé → $BackupDir" -ForegroundColor DarkGray
    }

    # --- Installation du nouveau build ---
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $TargetDir -Recurse -Force

    # --- Écriture du fichier de version (pour le check "déjà à jour" au prochain run) ---
    $LatestTag | Out-File -FilePath $VersionFile -Encoding ascii -NoNewline

    # --- Vérification finale ---
    $installedServer = Join-Path $TargetDir "llama-server.exe"
    if (-not (Test-Path $installedServer)) {
        Write-Host "[ERROR] Installation inconsistente : llama-server.exe manquant après copie." -ForegroundColor Red
        Write-Host "        Restauration du backup..." -ForegroundColor Yellow
        if (Test-Path $BackupDir) {
            if (Test-Path $TargetDir) { Remove-Item -Recurse -Force $TargetDir }
            Rename-Item -Path $BackupDir -NewName (Split-Path -Leaf $TargetDir)
        }
        & $cleanupTemp
        exit 1
    }

    Write-Host ""
    Write-Host "[SUCCESS] llama.cpp $LatestTag (CUDA 13) installé dans $TargetDir" -ForegroundColor Green
    Write-Host "          $($LatestTag) > .llamacpp-version (marqueur de version écrit)" -ForegroundColor DarkGray

    # --- Cleanup du backup ---
    if (-not $KeepBackup) {
        if (Test-Path $BackupDir) {
            Remove-Item -Recurse -Force $BackupDir
            Write-Host "[i] Backup .bak supprimé (-KeepBackup pour le conserver)." -ForegroundColor DarkGray
        }
    } else {
        Write-Host "[i] Backup conservé à $BackupDir (-KeepBackup)." -ForegroundColor DarkGray
    }

    & $cleanupTemp

} catch {
    Write-Host ""
    Write-Host "[ERROR] Échec de la mise à jour : $_" -ForegroundColor Red
    Write-Host "        Restauration du backup si présent..." -ForegroundColor Yellow
    if (Test-Path $BackupDir) {
        if (Test-Path $TargetDir) { Remove-Item -Recurse -Force $TargetDir -ErrorAction SilentlyContinue }
        Rename-Item -Path $BackupDir -NewName (Split-Path -Leaf $TargetDir) -ErrorAction SilentlyContinue
        Write-Host "        Build précédent restauré." -ForegroundColor Yellow
    }
    & $cleanupTemp
    exit 1
}

Write-Host ""
Write-Host "Découverte : llama_server.py détecte le GPU NVIDIA (nvidia-smi) et choisit" -ForegroundColor DarkGray
Write-Host "vendor/llamacpp-cuda13/ en priorité, puis vendor/llamacpp-cuda/ (legacy CUDA 12)," -ForegroundColor DarkGray
Write-Host "puis le PATH système (Vulkan/CPU). Sur machine NVIDIA récente, ce dossier est" -ForegroundColor DarkGray
Write-Host "celui utilisé automatiquement — rien à configurer." -ForegroundColor DarkGray
