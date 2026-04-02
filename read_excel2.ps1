$Excel = New-Object -ComObject Excel.Application
$Excel.Visible = $false
$Excel.DisplayAlerts = $false
$wb = $Excel.Workbooks.Open('C:\Users\wb.liujing23\lobsterai\project\temp_excel.xlsx')

Write-Host 'Sheets:'
foreach($sheet in $wb.Sheets) {
    Write-Host '  -' $sheet.Name
}

$ws = $null
foreach($sheet in $wb.Sheets) {
    if($sheet.Name -match '国内') {
        $ws = $sheet
        Write-Host 'Using sheet:' $sheet.Name
        break
    }
}

if($ws -eq $null) {
    $ws = $wb.Sheets.Item(1)
    Write-Host 'Using first sheet:' $ws.Name
}

Write-Host ''
Write-Host '=== Sheet structure (rows 33-43, cols A-J) ==='
for($row = 33; $row -le 43; $row++) {
    $rowData = @()
    for($col = 1; $col -le 10; $col++) {
        $val = $ws.Cells.Item($row, $col).Value()
        if($val -ne $null) {
            $rowData += "$([char](64+$col))=$val"
        }
    }
    if($rowData.Count -gt 0) {
        Write-Host "Row $row : " ($rowData -join ', ')
    }
}

Write-Host ''
Write-Host '=== C36:C39 and H36:H39 ==='
for($row = 36; $row -le 39; $row++) {
    $cVal = $ws.Cells.Item($row, 3).Value()
    $dVal = $ws.Cells.Item($row, 4).Value()
    $eVal = $ws.Cells.Item($row, 5).Value()
    $fVal = $ws.Cells.Item($row, 6).Value()
    $gVal = $ws.Cells.Item($row, 7).Value()
    $hVal = $ws.Cells.Item($row, 8).Value()
    $bVal = $ws.Cells.Item($row, 2).Value()
    Write-Host "Row $row : B=$bVal C=$cVal D=$dVal E=$eVal F=$fVal G=$gVal H=$hVal"
}

$wb.Close($false)
$Excel.Quit()
Write-Host ''
Write-Host 'Done'
