$Excel = New-Object -ComObject Excel.Application
$Excel.Visible = $false
$Excel.DisplayAlerts = $false
$wb = $Excel.Workbooks.Open('C:\Users\wb.liujing23\lobsterai\project\temp_excel.xlsx')

Write-Host 'Searching for 国内研究成本估算 sheet:'
$targetSheet = $null
$idx = 1
foreach($sheet in $wb.Sheets) {
    $name = $sheet.Name
    if($name -match '国内') {
        Write-Host "  Found at index $idx : $name"
        $targetSheet = $sheet
    }
    $idx++
}

if($targetSheet -eq $null) {
    Write-Host 'NOT FOUND - here are all sheets:'
    $wb.Sheets | ForEach-Object { Write-Host '  -' $_.Name }
} else {
    Write-Host ''
    Write-Host 'Using sheet: ' + $targetSheet.Name
    Write-Host ''
    Write-Host '=== C36:C39 and H36:H39 ==='
    for($row = 36; $row -le 39; $row++) {
        $cVal = $targetSheet.Cells.Item($row, 3).Value()
        $dVal = $targetSheet.Cells.Item($row, 4).Value()
        $eVal = $targetSheet.Cells.Item($row, 5).Value()
        $fVal = $targetSheet.Cells.Item($row, 6).Value()
        $gVal = $targetSheet.Cells.Item($row, 7).Value()
        $hVal = $targetSheet.Cells.Item($row, 8).Value()
        $bVal = $targetSheet.Cells.Item($row, 2).Value()
        Write-Host "Row $row : B=$bVal C=$cVal D=$dVal E=$eVal F=$fVal G=$gVal H=$hVal"
    }
    
    Write-Host ''
    Write-Host '=== Full rows 30-45 (cols A-J) ==='
    for($row = 30; $row -le 45; $row++) {
        $rowData = @()
        for($col = 1; $col -le 10; $col++) {
            $val = $targetSheet.Cells.Item($row, $col).Value()
            if($null -ne $val) {
                $colLetter = [char](64 + $col)
                $rowData += "$colLetter=$val"
            }
        }
        if($rowData.Count -gt 0) {
            Write-Host "Row $row : " ($rowData -join ', ')
        }
    }
}

$wb.Close($false)
$Excel.Quit()
