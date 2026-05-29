param(
    [string]$CsvPath = "C:\Users\hfaur\Downloads\CS- Working Doc - Cars (4).csv",
    [string]$OverridesPath = "C:\Program Files (x86)\Steam\steamapps\common\Automobilista 2\Vehicles\Textures\CustomLiveries\Overrides",
    [string]$OutputPath = "C:\Users\hfaur\OneDrive\Documents\New project\output\CS- Working Doc - Cars (4)-matched.csv",
    [string]$ReportPath = "C:\Users\hfaur\OneDrive\Documents\New project\output\ams2_override_match_report.csv"
)

function Normalize-Text {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    $value = $Text.ToLowerInvariant().Normalize([Text.NormalizationForm]::FormD)
    $chars = foreach ($char in $value.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($char) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            $char
        }
    }
    $value = -join $chars
    $value = $value -replace "mercedes-benz", "mercedes"
    $value = $value -replace "volkswagen", "vw"
    $value = $value -replace "chevrolet", "chevy"
    $value = $value -replace "cosworth", ""
    $value = $value -replace "[^a-z0-9]+", " "
    $value = $value -replace "\b(gen|model|race|cars|car|stock|classic|super|cup)\b", " "
    return (($value -replace "\s+", " ").Trim())
}

function Compact-Text {
    param([string]$Text)
    return ((Normalize-Text $Text) -replace "\s+", "")
}

function Get-Tokens {
    param([string]$Text)
    $normalized = Normalize-Text $Text
    if (-not $normalized) { return @() }
    return @($normalized.Split(" ", [StringSplitOptions]::RemoveEmptyEntries))
}

function Get-Jaccard {
    param([string]$Left, [string]$Right)
    $leftTokens = @(Get-Tokens $Left | Select-Object -Unique)
    $rightTokens = @(Get-Tokens $Right | Select-Object -Unique)
    if ($leftTokens.Count -eq 0 -or $rightTokens.Count -eq 0) { return 0.0 }
    $intersection = @($leftTokens | Where-Object { $rightTokens -contains $_ }).Count
    $union = @($leftTokens + $rightTokens | Select-Object -Unique).Count
    if ($union -eq 0) { return 0.0 }
    return [double]$intersection / [double]$union
}

$manualMatches = @{
    "Porsche 911 GT3 Cup 3.8" = "porsche_991_gt3"
    "Porsche 911 GT3 Cup 4.0" = "porsche_991_gt3_2"
    "Caterham 620R" = "caterham_620r"
    "Caterham Academy" = "caterham_academy"
    "Caterham Superlight" = "caterham_superlight"
    "Caterham Supersport" = "caterham_supersport"
    "Chevrolet Chevette" = "chevette"
    "Fiat Uno Classic B" = "uno_classicb"
    "Volkswagen Fusca Classic FL" = "fusca_classica"
    "Volkswagen Fusca" = "fusca_copa"
    "Volkswagen Fusca 1 Hot Cars" = "fusca_hotcars_m1"
    "Volkswagen Fusca 2 Hot Cars" = "fusca_hotcars_m2"
    "Volkswagen Gol Classic B" = "gol_classicb"
    "Volkswagen Gol Classic FL" = "gol_classica"
    "Volkswagen Gol Hot Cars" = "gol_hotcars"
    "Volkswagen Passat Classic B" = "pas_classicb"
    "Volkswagen Passat Classic FL" = "pas_classica"
    "Volkswagen Passat Hot Cars" = "pas_hotcars"
    "IVECO Stralis" = "ftruck_iveco"
    "MAN TGX" = "ftruck_man"
    "Mercedes-Benz Actros-2651" = "ftruck_merc"
    "Vulkan Truck" = "ftruck_vulkan"
    "Volkswagen Constellation" = "ftruck_vw"
    "Lola T95/00 Ford-Cosworth" = "cart_lola_t95_ford"
    "Lola T95/00 Mercedes-Benz" = "cart_lola_t95_mercedes"
    "Reynard 95i Ford-Cosworth" = "cart_reynard_95i_ford"
    "Reynard 95i Honda" = "cart_reynard_95i_honda"
    "Reynard 95i Mercedes-Benz" = "cart_reynard_95i_mercedes"
    "Lola T98/00 Ford-Cosworth" = "cart_lola_t98"
    "Reynard 98i Ford-Cosworth" = "cart_reynard_98i_ford"
    "Reynard 98i Honda" = "cart_reynard_98i_honda"
    "Reynard 98i Mercedes-Benz" = "cart_reynard_98i_mercedes"
    "Reynard 98i Toyota" = "cart_reynard_98i_toyota"
    "Swift 009c Ford-Cosworth" = "cart_swift_009c"
    "Lola B2K/00 Ford-Cosworth" = "cart_lola_b2k00_ford"
    "Lola B2K/00 Mercedes-Benz" = "cart_lola_b2k00_mercedes"
    "Lola B2K/00 Toyota" = "cart_lola_b2k00_toyota"
    "Reynard 2Ki Ford-Cosworth" = "cart_reynard_2ki_ford"
    "Reynard 2Ki Honda" = "cart_reynard_2ki_honda"
    "Reynard 2Ki Mercedes-Benz" = "cart_reynard_2ki_mercedes"
    "Reynard 2Ki Toyota" = "cart_reynard_2ki_toyota"
    "Formula Classic Gen1 Model1" = "formula_classic_g1m1"
    "Formula Classic Gen1 Model2" = "formula_classic_g1m2"
    "Formula Classic Gen2 Model1" = "formula_classic_g2m1"
    "Formula Classic Gen2 Model2" = "formula_classic_g2m2"
    "Formula Classic Gen2 Model3" = "formula_classic_g2m3"
    "Formula Classic Gen3 Model1" = "formula_classic_g3m1"
    "Formula Classic Gen3 Model2" = "formula_classic_g3m2"
    "Formula Classic Gen3 Model3" = "formula_classic_g3m3"
    "Formula Classic Gen3 Model4" = "formula_classic_g3m4"
    "Formula Classic Gen4 Model1" = "formula_classic_g4m1"
    "Formula Classic Gen4 Model2" = "formula_classic_g4m2"
    "Formula Classic Gen4 Model3" = "formula_classic_g4m3"
    "Formula HiTech Gen1 Model1" = "formula_hitech_g1m1"
    "Formula HiTech Gen1 Model2" = "formula_hitech_g1m2"
    "Formula HiTech Gen1 Model3" = "formula_hitech_g1m3"
    "Formula HiTech Gen1 Model4" = "formula_hitech_g1m4"
    "Formula HiTech Gen2 Model1" = "formula_hitech_g2m1"
    "Formula HiTech Gen2 Model2" = "formula_hitech_g2m2"
    "Formula HiTech Gen2 Model3" = "formula_hitech_g2m3"
    "Formula V8 Gen3" = "formula_reiza"
    "Formula Retro V12" = "formula_retro_v12"
    "Formula Retro V8" = "formula_retro_v8"
    "Formula Retro Gen2" = "formula_retro_g2"
    "Formula Retro Gen3 DFY" = "formula_retro_g3"
    "Formula Retro Gen3 Turbo" = "formula_retro"
    "Formula Ultimate Hybrid Gen2" = "formula_ultimate_2022"
    "Formula Ultimate Hybrid Gen3" = "formula_ultimate_2024"
    "Formula USA 2023" = "formula_usa_2023"
    "Formula V10 Gen1" = "formula_v10_g1"
    "Formula V10 Gen2" = "formula_v10"
    "Fórmula Inter MG15" = "formula_inter"
    "Formula Vee Gen1" = "formula_vee"
    "Formula Vee Gen1 Fin" = "formula_vee_fin"
    "Formula Vee Gen2" = "formula_vee_gen2"
    "Formula Trainer Advanced" = "formula_trainer_d"
    "Ginetta G40" = "ginetta_g40"
    "MCR S2000" = "mcr2000"
    "Metalmoro MRX Duratec P2" = "metalmoro_mrx_sharkfin"
    "Metalmoro MRX Honda P3" = "metalmoro_mrx_honda"
    "Metalmoro MRX Duratec P3" = "metalmoro_mrx_p3"
    "Metalmoro MRX Duratec P4" = "metalmoro_mrx"
    "Citroen DS3RX" = "citroen_ds3_rx"
    "Mini Countryman R60 RX" = "mini_rx"
    "Mitsubishi Lancer Evo10 RX" = "mitsubishi_lancer_rc"
    "Volkswagen Polo RX" = "vw_polo_rx"
    "Kartcross" = "rally_kart"
    "Kart 2-Stroke 125cc Direct" = "kart_01"
    "Kart 4-Stroke Race" = "kart_gx390"
    "Kart 4-Stroke Rental" = "kart_gx390_rental"
    "Kart 2-Stroke 125cc Shifter" = "kart_shifter"
    "Volkswagen Polo" = "vw_polo"
    "Volkswagen Polo GTS" = "vw_polo_gts"
    "Volkswagen Virtus" = "vw_virtus"
    "Volkswagen Virtus GTS" = "vw_virtus_gts"
    "Aussie Racing Camaro" = "arc_camaro"
    "Formula Edge Model1" = "formula_edge_g1m1"
    "Formula Edge Model2" = "formula_edge_g1m2"
    "Formula Edge Model3" = "formula_edge_g1m3"
}

$manualIdMatches = @{
    "212" = "cart_reynard_98i_honda"
    "213" = "cart_reynard_98i_mercedes"
    "214" = "cart_reynard_98i_toyota"
    "256" = "lotus_72e"
    "273" = "formula_vintage_g1m1"
    "274" = "formula_vintage_g1m2"
    "276" = "formula_vintage_g2m1"
    "277" = "formula_vintage_g2m2"
    "278" = "lotus_49c"
    "285" = "ginetta_g40_cup"
    "287" = "audi_v8_dtm"
    "288" = "bmw_m3_e30_a"
    "289" = "mercedes_evo2_dtm"
    "293" = "sauber_c9"
    "294" = "chevrolet_corvette_c3_rc"
    "295" = "chevrolet_corvette_c3_rcc"
    "296" = "porsche_911_rsr_74"
    "298" = "ultima_race"
    "312" = "mclaren_720s_gt3"
    "315" = "porsche_991_gt3r"
    "317" = "audi_r8_lms_gt3_evo2"
    "332" = "porsche_cayman_gt4cs"
    "333" = "ginetta_g40"
    "338" = "porsche_911_gte"
    "368" = "lola_b0540_lmp2"
    "369" = "lola_b0540_lmp2"
    "373" = "opala_oldstock"
    "380" = "metalmoro_ajr_gen2"
    "381" = "metalmoro_ajr_gen2"
    "397" = "opala_79"
    "398" = "opala_86"
    "400" = "stock_cruze"
    "401" = "stock_cruze_20"
    "402" = "stock_corolla"
    "403" = "stock_cruze_21"
    "404" = "stock_corolla_21"
    "405" = "stock_cruze_22"
    "406" = "stock_corolla_22"
    "407" = "stock_cruze_23"
    "408" = "stock_corolla_23"
    "409" = "stock_cruze_24"
    "410" = "stock_corolla_24"
    "411" = "stock_usa_g1"
    "412" = "stock_usa_g2"
    "413" = "stock_usa_g3"
    "414" = "stock_usa_g3_lm"
    "416" = "lamborghini_huracan_supertrofeo_evo2"
    "423" = "ultima"
    "424" = "superkart"
    "432" = "corvette_73"
    "435" = "mini_coopers_1965"
}

$rows = Import-Csv -LiteralPath $CsvPath
$folders = @(Get-ChildItem -LiteralPath $OverridesPath -Directory | ForEach-Object { $_.Name })
$folderSet = @{}
foreach ($folder in $folders) { $folderSet[$folder] = $true }

$report = @()
foreach ($row in $rows) {
    if ($row.Game -notmatch "AMS2") { continue }

    $match = ""
    $score = 0.0
    $reason = "blank"
    $carName = [string]$row.Car
    if ($manualIdMatches.ContainsKey([string]$row.id) -and $folderSet.ContainsKey($manualIdMatches[[string]$row.id])) {
        $match = $manualIdMatches[[string]$row.id]
        $score = 1.0
        $reason = "manual-id"
    } elseif ($manualMatches.ContainsKey($carName) -and $folderSet.ContainsKey($manualMatches[$carName])) {
        $match = $manualMatches[$carName]
        $score = 1.0
        $reason = "manual"
    } else {
        $carCompact = Compact-Text $row.Car
        $best = $null
        $second = $null
        foreach ($folder in $folders) {
            $folderWords = $folder -replace "[_-]+", " "
            $folderCompact = Compact-Text $folderWords
            $candidateScore = 0.0
            if ($carCompact -and $folderCompact -and ($carCompact -eq $folderCompact)) {
                $candidateScore = 0.99
            } elseif ($carCompact -and $folderCompact -and ($folderCompact.Contains($carCompact) -or $carCompact.Contains($folderCompact))) {
                $candidateScore = 0.86
            }
            $candidateScore = [Math]::Max($candidateScore, (Get-Jaccard $row.Car $folderWords))
            $candidateScore = [Math]::Max($candidateScore, ((Get-Jaccard "$($row.'Car class') $($row.Car)" $folderWords) * 0.95))
            $candidate = [pscustomobject]@{ Folder = $folder; Score = $candidateScore }
            if ($null -eq $best -or $candidate.Score -gt $best.Score) {
                $second = $best
                $best = $candidate
            } elseif ($null -eq $second -or $candidate.Score -gt $second.Score) {
                $second = $candidate
            }
        }
        if ($null -ne $best -and $best.Score -ge 0.72 -and ($null -eq $second -or ($best.Score - $second.Score) -ge 0.12)) {
            $match = $best.Folder
            $score = $best.Score
            $reason = "auto"
        }
    }

    if ($match) {
        $row.ams2_livery_folder = $match
    }

    $report += [pscustomobject]@{
        id = $row.id
        Car = $row.Car
        CarClass = $row.'Car class'
        Match = $match
        Score = [Math]::Round($score, 3)
        Reason = $reason
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
$rows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding UTF8
$report | Export-Csv -LiteralPath $ReportPath -NoTypeInformation -Encoding UTF8

$filled = @($report | Where-Object { $_.Match }).Count
$blank = @($report | Where-Object { -not $_.Match }).Count
Write-Output "AMS2 rows: $(@($report).Count)"
Write-Output "Matched: $filled"
Write-Output "Blank: $blank"
Write-Output "Output: $OutputPath"
Write-Output "Report: $ReportPath"
