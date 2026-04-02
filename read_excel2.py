import pandas as pd

path = r'C:\Users\wb.liujing23\AppData\Local\Temp\lobsterai\attachments\(UX)研究资源成本估算工具-v2.6-1775099052261-gae2yf.xlsx'
xl = pd.ExcelFile(path)
print('Sheets:', xl.sheet_names)
print()

sheet_name = '国内研究成本估算'
df = pd.read_excel(path, sheet_name=sheet_name, header=None)
print(f'Shape: {df.shape}')
print()
# Show rows 33-42 (0-indexed = Excel rows 34-43)
print('=== Rows 33-42 (Excel 34-43), Cols A-J ===')
print(df.iloc[33:43, 0:10].to_string())
print()
# Show C36-C39 (col 2, rows 35-38) and H36-H39 (col 7, rows 35-38)
print('=== C36-C39 (col index 2, rows 35-38) ===')
for i in range(35, 39):
    print(f'Row {i+1} (Excel {i+1}): C={repr(df.iloc[i, 2])}, H={repr(df.iloc[i, 7])}')
