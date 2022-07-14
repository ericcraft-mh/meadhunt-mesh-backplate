from ctypes import alignment
from os.path import exists
from typing import List
from pxr import Usd, UsdGeom, UsdShaders
import omni.kit.ui
import omni.ui as ui
import omni.usd
import os
import re
from omni.ui import color as cl
from PIL import Image
from omni.kit.window.filepicker.dialog import FilePickerDialog
from pxr import Sdf,UsdShade,UsdUtils
from pxr.Gf import Vec3d
import math

class ExtensionWindow(ui.Window):
    
    # Class Variables
    LABEL_WIDTH = 80
    SPACER_WIDTH = 5
    BUTTON_SIZE = 24
    COMBO_CAMS = ui.ComboBox()
    CAMS_LIST =[]
    PATHS_LIST = []
    STAGE = omni.usd.get_context().get_stage()
    BACKPLATE = None

    def __init__(self, title, win_width, win_height, menu_path):
        super().__init__(title, width=win_width, height=win_height)
        self._menu_path = menu_path
        self._file_return = None
        self._open_file_dialog = None
        self._backplate_name = None
        self._old_prim_path = None
        # self.STAGE = omni.usd.get_context().get_stage()
        self.set_visibility_changed_fn(self._on_visibility_changed)
        self._get_cameras()
        self._build_ui()

    def on_shutdown(self):
        if self:
            self.hide()
            self.destroy()
            self = None

    def destroy(self):
        if self:
            self = None

    def show(self):
        self.visible = True
        self.focus()

    def hide(self):
        self.visible = False

    def _get_cameras(self):
        # Create empty lists to add cameras and prim paths to
        self.CAMS_LIST = []
        self.PATHS_LIST = []
        # Safety check maket sure there is a self.STAGE
        if self.STAGE == None:
            self.STAGE = omni.usd.get_context().get_stage()
        for prim in self.STAGE.Traverse():
            # Get Cameras and make sure they are perspective
            if prim.IsA(UsdGeom.Camera) and prim.GetProperty('projection').Get() == 'perspective':
                # Create a list of names
                self.CAMS_LIST.append(prim.GetName())
                # Create a list of paths
                self.PATHS_LIST.append(prim.GetPath())

    def _fill_combo(self, combo:ui.ComboBox):
        # Get the current index of the selected item
        currentIndex = combo.model.get_item_value_model().as_int
        # # Get the current name of the item
        currentItem = self.CAMS_LIST[currentIndex]
        self._get_cameras()
        # Get the new Index based on the name
        # Use try except in case camera has been deleted
        # Fallback to 0 if not in the list
        try:
            newIndex = self.CAMS_LIST.index(currentItem)
        except ValueError:
            newIndex = 0
        # Clear the list
        for items in combo.model.get_item_children():
            combo.model.remove_item(items)
        # Rebuild the list with the new list
        for item in self.CAMS_LIST:
            combo.model.append_child_item(None, ui.SimpleStringModel(item))
        # Set the new index value so the selection stays with the name not the index value
        combo.model.get_item_value_model().set_value(newIndex)
    
    def _set_scale(self,cam_path:Sdf.Path,distance:float):
        if self.STAGE == None:
            self.STAGE = omni.usd.get_context().get_stage()
        cam_prim = self.STAGE.GetPrimAtPath(cam_path)
        cam_focal = cam_prim.GetAttribute('focalLength').Get()
        cam_hAperture = cam_prim.GetAttribute('horizontalAperture').Get()
        cam_vAperture = cam_prim.GetAttribute('verticalAperture').Get()
        hfov = math.tan(math.atan(cam_hAperture/(cam_focal*2.0)))
        vfov = math.tan(math.atan(hfov/(cam_hAperture/cam_vAperture)))
        res_model = self._res_field.model
        res_children = res_model.get_item_children()
        rwidth = res_model.get_item_value_model(res_children[0]).get_value_as_int()
        rheight = res_model.get_item_value_model(res_children[1]).get_value_as_int()
        xscale = (hfov*distance)/50.0
        yscale = xscale/(rwidth/rheight)
        # twidth = 1920.0
        # theight = 1080.0
        # (twidth/theight)/(rwidth/rheight)
        return Vec3d(xscale,yscale,1.0)

    def _build_ui(self):
        with self.frame:
            with ui.VStack(height=0):
                with ui.VStack(spacing=5, name='frame_v_stack'):
                    self.COMBO_CAMS = self._create_combo('Cameras:', self.CAMS_LIST, 0)
                    self.COMBO_CAMS.set_mouse_pressed_fn(lambda a,b,c,d:self._fill_combo(self.COMBO_CAMS))
                    with ui.HStack():
                        ui.Label('Name:', name='namelabel', width=self.LABEL_WIDTH)
                        self._backplate_name = ui.StringField(name='namefield', height=self.BUTTON_SIZE).model
                        self._backplate_name.set_value('BackPlate')
                    self._texture_field = self._create_path(str='Texture:',paths='')
                    with ui.HStack():
                        ui.Label('Resolution:',name='resLbl', width=self.LABEL_WIDTH)
                        self._res_field = ui.MultiIntDragField(1920, 1080, name='resIntField', min=1, max=16384, h_spacing=5)
                    with ui.HStack():
                        ui.Label('Distance:', name='distancelabel', width=self.LABEL_WIDTH)
                        self._distance_field = ui.FloatField(width=50)
                        ui.Spacer(width=5.0)
                        self._distance_slider = ui.FloatSlider(min=1, max=1000, step=1.0)
                        # Link field and slider
                        self._distance_slider.model = self._distance_field.model
                        self._distance_slider.model.set_value(200.0)
                        self._distance_slider.model.add_value_changed_fn(lambda a: self._set_plane(a))
                ui.Spacer(height=2)
                self.btn_click = ui.Button('Set BackPlate', name='BtnClick', clicked_fn=lambda: self._set_plane())

    def _on_filter_files(self, item) -> bool:
        '''Callback to filter the choices of file names in the open or save dialog'''
        # if self.DEBUG:
        #     print(f'current_filter_option: {self._open_file_dialog.current_filter_option}')
        if not item or item.is_folder:
            return True
        if self._open_file_dialog.current_filter_option == 0:
            # Show only files with listed extensions
            return item.path.endswith(('.bmp','.dds','.exr','.gif','.hdr','.jpeg','.jpg','.png','.psd','.tga'))
        else:
            # Show All Files (*)
            return True

    def _create_path(self, str, paths, lbl_name='label', str_name='path'):
        with ui.HStack(style={'Button':{'margin':0.0}}):
            ui.Label(str, name=lbl_name, width=self.LABEL_WIDTH)
            field = ui.StringField(name=str_name, height=self.BUTTON_SIZE).model
            field.set_value(paths)
            ui.Spacer(width=5.0)
            ui.Button(image_url='resources/icons/folder.png', width=self.BUTTON_SIZE, height=self.BUTTON_SIZE, clicked_fn=lambda: self._texture_file(self._texture_field))
        return field

    def _create_combo(self, str, items, selected, lbl_name='label', cmb_name='combo'):
        with ui.HStack():
            ui.Label(str, name=lbl_name, width=self.LABEL_WIDTH)
            combo = ui.ComboBox(selected, name=cmb_name)
            for item in items:
                combo.model.append_child_item(None, ui.SimpleStringModel(item))
        return combo

    def _set_plane(self, a=None):
        # implement soft range to grow slider if value is greater that max
        if a != None and a.get_value_as_float() > self._distance_slider.max:
            self._distance_slider.max = a.get_value_as_float()
        self._old_prim_path = None
        if self.STAGE == None:
            self.STAGE = omni.usd.get_context().get_stage()
        for prim in self.STAGE.Traverse():
            if prim.IsValid() and prim.IsA(UsdGeom.Mesh) and prim.GetName() == self._backplate_name.get_value_as_string():
                self._old_prim_path = prim.GetPath()
        if self._old_prim_path == None:
            result, oldPath = omni.kit.commands.execute('CreateMeshPrimWithDefaultXform',prim_type='Plane')
            if result:
                self._old_prim_path = oldPath
        # print(self._old_prim_path)
        camPath = str(self.PATHS_LIST[self.COMBO_CAMS.model.get_item_value_model().as_int])
        self.BACKPLATE = f'{camPath}/{self._backplate_name.get_value_as_string()}'
        prim_path = self.BACKPLATE
        if self._old_prim_path != prim_path:
            omni.kit.commands.execute('MovePrim',path_from=str(self._old_prim_path),path_to=self.BACKPLATE)
        prim = self.STAGE.GetPrimAtPath(self.BACKPLATE)
        # Reset xformOp to align with camera parent
        prim.GetAttribute('xformOp:translate').Set(Vec3d(0,0,-self._distance_field.model.get_value_as_float()))
        prim.GetAttribute('xformOp:rotateXYZ').Set(Vec3d(0,0,0))
        prim.GetAttribute('xformOp:scale').Set(self._set_scale(camPath,self._distance_field.model.get_value_as_float()))
        # Material fun
        scriptdir = os.path.dirname(__file__)
        joinpath = os.path.join(scriptdir,'../../../assets/BackPlate.mdl')
        mdlfile = os.path.abspath(joinpath)
        if exists(mdlfile):
            mtlname = self._backplate_name.get_value_as_string()
            mtlpath = f'/World/Looks/{mtlname}'
            mtlfound = False
            inputimage = None
            for prim in self.STAGE.Traverse():
                if (prim.GetPath() == mtlpath):
                    print('material found: ',mtlpath)
                    mtlfound = True
                    break
            if not mtlfound:
                omni.kit.commands.execute('CreateMdlMaterialPrim',mtl_url=mdlfile,mtl_name=mtlname,mtl_path=mtlpath)
                # omni.kit.commands.execute('BindMaterial',prim_path=[self.BACKPLATE],material_path=Sdf.Path(mtlpath),strength='weakerThanDescendants')
                # omni.kit.commands.execute('ChangeProperty',prop_path=Sdf.Path(f'{mtlpath}/Shader.inputs:emission_image'),value=Sdf.AssetPath(self._texture_field.get_value_as_string()),type_to_create_if_not_exist=Sdf.ValueTypeName('asset'),prev=None)
                mtlfound = True
            print('mtlfound: ',mtlfound)
            mtlprim = self.STAGE.GetPrimAtPath(mtlpath)
            # omni.usd.create_material_input(mtlprim,'emission_image',Sdf.AssetPath(self._texture_field.get_value_as_string()),Sdf.ValueTypeNames.Asset)
            shaderprim = self.STAGE.GetPrimAtPath(Sdf.Path(f'{mtlpath}/Shader'))
            inputs = UsdShade.Shader(shaderprim).GetInputs()
            print('inputs: ',inputs)
            print('count: ',int(inputs.count))
            if inputs.count == 0:
                omni.usd.create_material_input(mtlprim,'emission_image',Sdf.AssetPath(self._texture_field.get_value_as_string()),Sdf.ValueTypeNames.Asset)
            inputs = UsdShade.Shader(shaderprim).GetInputs()
            print('inputs: ',inputs)
            # if mtlfound:

            #     print('shaderprim: ',shaderprim)
                
            #     print('inputs: ',inputs)
            #     for input in inputs:
            #         print(input.GetBaseName())
            #         if input.GetBaseName() == 'emission_image':
            #             inputimage = input
            #             break
            #     print('inputimage: ',inputimage)
            # if inputimage != None and self._texture_field.get_value_as_string() != '':
            #     print('prop_path: ',Sdf.Path(f'{mtlpath}/Shader.inputs:emission_image'))
            #     print('value: ',Sdf.AssetPath(self._texture_field.get_value_as_string()))
            #     inputimage.Set(Sdf.AssetPath(self._texture_field.get_value_as_string()))
            #     # omni.kit.commands.execute('ChangeProperty',prop_path=Sdf.Path(f'{mtlpath}/Shader.inputs:emission_image'),value=Sdf.AssetPath(self._texture_field.get_value_as_string()),type_to_create_if_not_exist=Sdf.AssetPath(),prev=None)
        
    def _fix_path(self, str):
        txt = re.split(r'[/\\]',str)
        return '/'.join(txt)

    def _texture_file(self, field):
        def _on_click_open(file_name: str, directory_path: str):
            '''Callback executed when the user selects a file in the open file dialog'''
            if file_name != '' and directory_path != None:
                self._file_return = os.path.join(directory_path, file_name)
                self._file_return = self._fix_path(self._file_return)
                # self._valid_xml = xml_data(self.DEBUG, self._file_return).valid_xml()

            if self._file_return:
                field.set_value(self._file_return)
                if self._open_file_dialog:
                    self._open_file_dialog.hide()

            if os.path.exists(self._file_return):
                self.btn_click.enabled = True
                ui.set_shade('white')
            else:
                self.btn_click.enabled = False
                ui.set_shade('transparent')

        def _on_click_cancel(file_name: str, directory_path: str):
            field.set_value('')
            self.btn_click.enabled = False
            ui.set_shade('transparent')
            if self._open_file_dialog:
                self._open_file_dialog.hide()

        if self._open_file_dialog:
            self._open_file_dialog.hide()
            self._open_file_dialog.destroy()

        # self._open_file_dialog = FilePickerDialog(
        #         'Select XML File',
        #         apply_button_label='Select',
        #         click_apply_handler=lambda f, d: _on_click_open(f, d),
        #         click_cancel_handler=lambda f, d: _on_click_cancel(f, d),
        #         file_extension_options = [('*.xml', 'Files (*.xml)')],
        #         # item_filter_fn=lambda item: self._on_filter_xml(item)
        #     )
        self._open_file_dialog = FilePickerDialog(
            'Open BackPlate File',
            apply_button_label='Open',
            click_apply_handler=lambda f, d: _on_click_open(f, d),
            click_cancel_handler=lambda f, d: _on_click_cancel(f, d),
            item_filter_options= ['Textures (*.bmp,*.dds,*.exr,*.gif,*.hdr,*.jpeg,*.jpg,*.png,*.psd,*.tga)','All Files (*.*)'],
            item_filter_fn=lambda item: self._on_filter_files(item)
        )
        self._open_file_dialog.show()

    def _on_visibility_changed(self, visible):
        if not visible:
            omni.kit.ui.get_editor_menu().set_value(self._menu_path, False)