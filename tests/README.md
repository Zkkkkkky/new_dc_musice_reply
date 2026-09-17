# 测试

自动化测试、测试夹具和最小复现放在此目录。测试生成物应写入 `build/` 或系统临时目录。

运行：

```powershell
python -m unittest discover -s tests -v
```

当前测试锁定两份源 ROM 与交付 ROM 的 SHA-256，并验证旧文件体、扩容布局、FCEUX 清锁代码和 15 曲命令表。
