import omni.ext
import omni.ui as ui
import omni.kit.ui

from .window import ExtensionWindow
# Any class derived from `omni.ext.IExt` in top level module (defined in `python.modules` of `extension.toml`) will be
# instantiated when extension gets enabled and `on_startup(ext_id)` will be called. Later when extension gets disabled
# on_shutdown() is called.
class BackPlate(omni.ext.IExt):
    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.

    WINDOW_TITLE = "BackPlate"

    def on_startup(self, ext_id):
        print("[meadhunt.mesh.backplate] BackPlate startup")

        self._menu_path = f"Window/Mead & Hunt/{self.WINDOW_TITLE}"
        self._window = None
        self._menu = omni.kit.ui.get_editor_menu().add_item(self._menu_path, self._on_menu_click, True)
        self._window = ExtensionWindow(self.WINDOW_TITLE, 300, 300, self._menu_path)
        omni.kit.ui.get_editor_menu().set_value(self._menu_path, True)

    def on_shutdown(self):
        print("[meadhunt.mesh.backplate] BackPlate shutdown")

        if self._window:
            self._window.hide()
            self._window.destroy()
            self._window = None   

        omni.kit.ui.get_editor_menu().remove_item(self._menu)

    def _on_menu_click(self, menu, toggled):
        """Handles showing and hiding the window from the 'Windows' menu."""
        if toggled:
            if self._window is None:
                self._window = ExtensionWindow(self.WINDOW_TITLE, 300, 300, self._menu_path)
            else:
                self._window.show()
        else:
            if self._window:
                self._window.hide()
                self._window.destroy()

    def destroy(self):
        if self._window:
            self._window.hide()
            self._window = None