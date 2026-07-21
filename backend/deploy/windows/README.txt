Question Bank —— 内网服务器安装说明(Windows)
================================================

推荐:直接运行安装程序(最简单)
--------------------------------
1. 双击 QuestionBank-Setup-x.y.z.exe
2. 弹出“是否允许更改”时点“是”
3. 按向导点“下一步 → 安装 → 完成”

安装程序会自动:装到 Program Files、注册开机自启的后台服务、
放行防火墙端口、在开始菜单创建“打开题库/卸载题库”快捷方式。
全程无需命令行。

首次使用
--------
在服务器本机浏览器打开 http://localhost:8000 完成安装向导
(选择数据库、创建管理员账号)。之后其他终端即可访问。
(也可用开始菜单的“打开题库”。)

其他终端访问
------------
浏览器打开 http://<服务器IP>:8000
查看本机 IP:在命令提示符运行 ipconfig,找 IPv4 地址。

卸载
----
Windows“设置 → 应用”里找到 Question Bank 卸载,或用开始菜单“卸载题库”。
卸载会停止并移除服务、删除防火墙规则;应用数据不会被删除。

数据与日志
----------
- 应用数据(数据库、config.json、上传文件)在 C:\ProgramData\QuestionBank,
  升级不会丢数据。备份/迁移直接复制该目录即可。
- 服务日志在安装目录下的 question-bank-service.out.log / .err.log。

--------------------------------------------------------------------
高级(手动)方式 —— 一般用户无需理会
--------------------------------------------------------------------
安装目录内附带以下工具,供需要脚本化 / 自定义端口的运维使用:

  question-bank-service.exe  服务包装器(WinSW)
  question-bank-service.xml  服务配置(端口、监听地址等)
  install-service.ps1        手动注册服务 + 放行防火墙
  uninstall-service.ps1      手动卸载服务 + 移除防火墙规则

常用操作(管理员 PowerShell,在安装目录):
  查看状态: .\question-bank-service.exe status
  停止:     .\question-bank-service.exe stop
  启动:     .\question-bank-service.exe start
  重启:     .\question-bank-service.exe restart

修改端口:编辑 question-bank-service.xml 中 <env name="PORT" .../> 的值,
然后以管理员运行:  .\question-bank-service.exe restart
并同步更新防火墙:  .\install-service.ps1 -Port <新端口>
