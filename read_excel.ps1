$Excel = New-Object -ComObject Excel.Application
$Excel.Visible = $false
$Excel.DisplayAlerts = $false
$wb = $Excel.Workbooks.Open('C:\Users\wb.liujing23\AppData\Local\Temp\lobsterai\attachments\(UX)研究资源成本估算工具-v2.6-1775099052261-gae2yf.xlsx')

Write-Host 'Sheets:'
foreach($sheet in $wb.Sheets) {
    Write-Host '  -' $sheet.Name
}

# Find 国内研究成本估算 sheet
$ws = $null
foreach($sheet in $wb.Sheets) {
    if($sheet.Name -match '国内') {
        $ws = $sheet
        Write-Host 'Found sheet:' $sheet.Name
        break
    }
}

if($ws -eq $null) {
    Write-Host 'Sheet not found, using first sheet'
    $ws = $wb.Sheets.Item(1)
}

# Read C36:H39 range
Write-Host ''
Write-Host 'C36:H39 values:'
for($row = 36; $row -le 39; $row++) {
    $cVal = $ws.Cells.Item($row, 3).Value()
    $dVal = $ws.Cells.Item($row, 4).Value()
    $eVal = $ws.Cells.Item($row, 5).Value()
    $fVal = $ws.Cells.Item($row, 6).Value()
    $gVal = $ws.Cells.Item($row, 7).Value()
    $hVal = $ws.Cells.Item($row, 8).Value()
    $c2 = $ws.Cells.Item($row, 2).Value()
    Write-Host "Row $row (B=$c2): C=$cVal, D=$dVal, E=$eVal, F=$fVal, G=$gVal, H=$hVal"
}

$wb.Close($false)
$Excel.Quit()
