"""macOS Dock / 应用菜单集成(仅在 macOS 上由 ``app.tray`` 导入)。

pystray 只管菜单栏图标,不给 NSApplication 设 delegate。打包成 .app 后 Dock 图标会显示,
但如果不处理,点 Dock 图标没有任何反应,⌘Q / Dock「退出」/ 注销也不会停掉服务。这里补上:

* 点 Dock 图标、或在 Finder 里再次打开 .app(reopen 事件)→ 打开题库;
* Dock 右键菜单 →「打开题库」(系统自带「退出」);
* 应用菜单「退出 xxx」(⌘Q)、Dock「退出」、注销关机 → 先停服务再退出。

AppKit 只能在主线程操作:``install`` 必须在主线程、``pystray.Icon`` 创建之后、``icon.run()``
之前调用;其他线程用 ``refresh`` 更新菜单文字,它会转到主线程执行。
"""
from __future__ import annotations

from typing import Callable, Optional

import AppKit  # type: ignore
import Foundation  # type: ignore
import objc  # type: ignore
from PyObjCTools import AppHelper  # type: ignore

_delegate: Optional["_AppDelegate"] = None  # NSApp 对 delegate 是弱引用,必须自己持有


class _AppDelegate(Foundation.NSObject, protocols=[objc.protocolNamed("NSApplicationDelegate")]):
    def initWithCallbacks_(self, callbacks):  # noqa: N802 - Objective-C selector
        self = objc.super(_AppDelegate, self).init()
        if self is None:
            return None
        self._callbacks = callbacks
        return self

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):  # noqa: N802
        self._callbacks["open"]()
        return False

    def applicationShouldTerminate_(self, _app):  # noqa: N802
        try:
            self._callbacks["terminate"]()
        except Exception:  # noqa: BLE001 - 无论如何都要允许退出
            pass
        return AppKit.NSTerminateNow

    def applicationDockMenu_(self, _app):  # noqa: N802
        menu = AppKit.NSMenu.alloc().init()
        item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self._callbacks["open_title"](), "openUI:", ""
        )
        item.setTarget_(self)
        menu.addItem_(item)
        return menu

    @objc.IBAction
    def openUI_(self, _sender):  # noqa: N802
        self._callbacks["open"]()


def _build_main_menu(quit_title: str) -> None:
    main = AppKit.NSMenu.alloc().init()
    app_item = AppKit.NSMenuItem.alloc().init()
    main.addItem_(app_item)
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu.addItemWithTitle_action_keyEquivalent_(quit_title, "terminate:", "q")
    app_item.setSubmenu_(app_menu)
    AppKit.NSApplication.sharedApplication().setMainMenu_(main)


def install(
    on_open: Callable[[], None],
    on_terminate: Callable[[], None],
    open_title: Callable[[], str],
    quit_title: Callable[[], str],
) -> None:
    global _delegate
    callbacks = {
        "open": on_open,
        "terminate": on_terminate,
        "open_title": open_title,
        "quit_title": quit_title,
    }
    _delegate = _AppDelegate.alloc().initWithCallbacks_(callbacks)
    AppKit.NSApplication.sharedApplication().setDelegate_(_delegate)
    _build_main_menu(quit_title())


def refresh() -> None:
    """语言切换后重建应用菜单(可在任意线程调用)。"""
    if _delegate is None:
        return
    AppHelper.callAfter(_build_main_menu, _delegate._callbacks["quit_title"]())
