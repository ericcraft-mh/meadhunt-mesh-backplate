from ctypes import alignment
import os
from os.path import exists
import re
import math
from PIL import Image

from pxr import Usd, UsdGeom, Sdf, UsdShade, Tf
from pxr.Gf import Vec3d

import carb.tokens

import omni.kit.ui
import omni.ui as ui
import omni.usd
from omni.ui import color as cl
from omni.kit.window.filepicker.dialog import FilePickerDialog

class ExtensionWindow(ui.Window):
    
    # Class Variables
    LABEL_WIDTH = 80
    SPACER_WIDTH = 5
    BUTTON_SIZE = 24
    COMBO_CAMS = ui.ComboBox()
    CAMS_LIST =[]
    PATHS_LIST = []
    STAGE = omni.usd.get_context().get_stage()

    def __init__(self, title, win_width, win_height, menu_path):
        super().__init__(title, width=win_width, height=win_height)
        self._menu_path = menu_path
        self._file_return = None
        self._open_file_dialog = None
        self._backplate_name = None
        self._old_prim_path = None
        self._stage = None
        self._get_stage()
        self.set_visibility_changed_fn(self._on_visibility_changed)
        if self._stage != None:
            self._fill_combo(self.COMBO_CAMS)
        self._build_ui()
        self._fill_ui(self._get_backplate())

    def on_shutdown(self):
        if self:
            self.hide()
            self.destroy()
            self = None

    def on_startup(self):
        self._get_stage()
        if self._stage != None:
            self._fill_combo(self.COMBO_CAMS)

    def destroy(self):
        if self:
            self = None

    def show(self):
        self.visible = True
        self.focus()

    def hide(self):
        self.visible = False

    def _get_stage(self):
        '''Get stage if it is currently None'''
        if self._stage == None:
            self._stage = omni.usd.get_context().get_stage()
# 
# The fun Defs
# 
    def _get_render_resolution(self):
        '''Get and Return resolution from RenderProduct_Viewport'''
        # Make sure stage is set
        self._get_stage()
        # Get scene render resolution
        renderproduct = self._stage.GetPrimAtPath(Sdf.Path('/Render/RenderProduct_Viewport'))
        view_res = renderproduct.GetAttribute('resolution').Get()
        return view_res
        
    def _get_cameras(self):
        '''Get scene persepctive cameras, return tuple(list,list) for camera names and paths'''
        # Create empty lists to add cameras and prim paths to
        self.CAMS_LIST = []
        self.PATHS_LIST = []
        # Safety check make sure there is a self._stage
        self._get_stage()
        for prim in self._stage.Traverse():
            # Get Cameras and make sure they are perspective
            if prim.IsA(UsdGeom.Camera) and prim.GetProperty('projection').Get() == 'perspective':
                # Create a list of names
                self.CAMS_LIST.append(prim.GetName())
                # Create a list of paths
                self.PATHS_LIST.append(prim.GetPath())
    
    def _get_backplate(self):
        cams_int = self.COMBO_CAMS.model.get_item_value_model().as_int
        cam = str(self.CAMS_LIST[cams_int])
        backplate = f'{self._backplate_name.get_value_as_string()}_{cam}'
        path = f'{str(self.PATHS_LIST[cams_int])}/{backplate}'
        prim = self._stage.GetPrimAtPath(path)
        if prim.IsValid():
            return prim
        else:
            return None

    def _calc_scale(self,cam_path:Sdf.Path,distance:float,fit:int=0):
        '''Calculate Scale for BackPlate based on camera, backplate image, and backplate mesh values'''
        self._get_stage()
        img = None
        cam_prim = self._stage.GetPrimAtPath(cam_path)
        cam_focal = cam_prim.GetAttribute('focalLength').Get()
        cam_hAperture = cam_prim.GetAttribute('horizontalAperture').Get()
        # cam_vAperture = cam_prim.GetAttribute('verticalAperture').Get()
        hfov = math.tan(math.atan(cam_hAperture/(cam_focal*2.0)))
        # vfov = math.tan(math.atan(hfov/(cam_hAperture/cam_vAperture)))
        rendWidth,rendHeight = self._get_render_resolution()
        resaspect = rendWidth/rendHeight
        imgpath = self._texture_field.get_value_as_string()
        if imgpath != '':
            img = Image.open(self._texture_field.get_value_as_string())
        else:
            mtlname = self._backplate_name.get_value_as_string()
            mtlpath = f'/World/Looks/{mtlname}'
            mtlprim = self._stage.GetPrimAtPath(mtlpath)
            if mtlprim:
                shaderobj = omni.usd.get_shader_from_material(mtlprim)
                input = UsdShade.Shader(shaderobj).GetInput('emission_image')
                if input and input.Get().path != '':
                    img = Image.open(input.Get().path)
        if img:
            imgw,imgh = img.size
        else:
            imgw = rendWidth
            imgh = rendHeight
        txtraspect = imgw/imgh
        xscale = (hfov*distance)/50.0
        if fit==0:
            yscale = xscale/resaspect
            xscale *= txtraspect/resaspect
        else:
            yscale = xscale/txtraspect
        if UsdGeom.GetStageUpAxis(self._stage) != 'Z':
            return Vec3d(xscale,1.0,yscale)
        else:
            return Vec3d(xscale,yscale,1.0)

    def _del_plane(self):
        '''Delete BackPlate and assigned material'''
        prim = self._get_backplate()
        paths = []
        if prim:
            paths = list(set([prim.GetPath()]+UsdShade.MaterialBindingAPI(prim).GetDirectBindingRel().GetTargets()))
        omni.kit.commands.execute('DeletePrims',paths=paths)

    def _auto_create(self,do:bool=True,max:float=None):
        prim = None
        prim = self._get_backplate()
        if do or prim:
            self._set_plane(max)

    def _set_plane(self, max:float=None, fit:int=0):
        # implement soft range to grow slider if value is greater that max
        if max != None and max > self._distance_slider.max:
            self._distance_slider.max = max*1.1
        self._old_prim_path = None
        self._get_stage()
        cams_int = self.COMBO_CAMS.model.get_item_value_model().as_int
        primname = f'{self._backplate_name.get_value_as_string()}_{str(self.CAMS_LIST[cams_int])}'
        for prim in self._stage.Traverse():
            if prim.IsValid() and prim.IsA(UsdGeom.Mesh) and prim.GetName() == primname:
                self._old_prim_path = prim.GetPath()
        if self._old_prim_path == None:
            result, oldPath = omni.kit.commands.execute('CreateMeshPrimWithDefaultXform',prim_type='Plane')
            if result:
                self._old_prim_path = oldPath
        camPath = str(self.PATHS_LIST[cams_int])
        prim_path = f'{camPath}/{primname}'
        if self._old_prim_path != prim_path:
            omni.kit.commands.execute('MovePrim',path_from=str(self._old_prim_path),path_to=prim_path)
        prim = self._stage.GetPrimAtPath(prim_path)
        prim_z = prim.GetAttribute('xformOp:translate').Get()[2]
        if prim_z > 0.0:
            self._distance_field.model.set_value(prim_z)
        # Create primvars for doNotCastShadows and invisibleToSecondaryRays
        shadows_attrib = prim.CreateAttribute('primvars:doNotCastShadows',Sdf.ValueTypeNames.Bool)
        secondaryRays_attrib = prim.CreateAttribute('primvars:invisibleToSecondaryRays',Sdf.ValueTypeNames.Bool)
        # Set the Values based on UI settings
        shadows_attrib.Set(not self._cb_shadows.model.get_value_as_bool())
        secondaryRays_attrib.Set(self._cb_secondary.model.get_value_as_bool())
        # Reset xformOp to align with camera parent
        prim.GetAttribute('xformOp:translate').Set(Vec3d(0,0,-self._distance_field.model.get_value_as_float()))
        if UsdGeom.GetStageUpAxis(self._stage) != 'Z':
            prim.GetAttribute('xformOp:rotateXYZ').Set(Vec3d(90,0,180))
        else:
            prim.GetAttribute('xformOp:rotateXYZ').Set(Vec3d(0,0,0))
        canvas_attrib = prim.CreateAttribute('canvas_fill',Sdf.ValueTypeNames.Int)
        canvas_attrib.Set(self.COMBO_FIT.model.get_item_value_model().get_value_as_int())
        prim.GetAttribute('xformOp:scale').Set(self._calc_scale(camPath,self._distance_field.model.get_value_as_float(),prim.GetAttribute('canvas_fill').Get()))
        # Material fun
        # Use carb.tokens to resolve path to mdl
        rootpath = carb.tokens.get_tokens_interface().resolve("${meadhunt.mesh.backplate}")
        mdlfile = rootpath+"/assets/BackPlate.mdl"
        if exists(os.path.abspath(mdlfile)):
            mtlname = primname
            mtlpath = f'/World/Looks/{mtlname}'
            mtlfound = False
            inputimage = None
            isimage = False
            for prim in self._stage.Traverse():
                if (prim.GetPath() == mtlpath):
                    mtlfound = True
                    break
            if not mtlfound:
                omni.kit.commands.execute('CreateMdlMaterialPrim',mtl_url=mdlfile,mtl_name=mtlname,mtl_path=mtlpath)
                mtlfound = True
            mtlprim = self._stage.GetPrimAtPath(mtlpath)
            shaderprim = self._stage.GetPrimAtPath(mtlpath+"/Shader")
            shaderobj = omni.usd.get_shader_from_material(mtlprim)
            if shaderprim.GetAttribute("info:mdl:sourceAsset").Get() != Sdf.AssetPath(mdlfile):
                shaderprim.GetAttribute("info:mdl:sourceAsset").Set(Sdf.AssetPath(mdlfile))
            if shaderprim.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get() != "BackPlate":
                shaderprim.GetAttribute("info:mdl:sourceAsset:subIdentifier").Set("BackPlate")
            if not shaderprim.GetAttribute('inputs:dbl_sided').Get():
                shaderprim.CreateAttribute('inputs:dbl_sided',Sdf.ValueTypeNames.Bool)
            shaderprim.GetAttribute('inputs:dbl_sided').Set(self._cb_dblsided.model.get_value_as_bool())
            inputimage = shaderprim.GetAttribute('inputs:emission_image')
            if inputimage.Get() != None:
                if inputimage.Get().path != '':
                    isimage = True
            if inputimage.Get() == None or not isimage:
                omni.usd.create_material_input(mtlprim,'emission_image',Sdf.AssetPath(self._texture_field.get_value_as_string()),Sdf.ValueTypeNames.Asset)
                omni.kit.commands.execute('BindMaterial',prim_path=[prim_path],material_path=Sdf.Path(mtlpath),strength='weakerThanDescendants')
                inputimage = UsdShade.Shader(shaderobj).GetInput('emission_image')   
                if inputimage:
                    isimage = True
            else:
                prim = self._stage.GetPrimAtPath(prim_path)
                if not len(UsdShade.MaterialBindingAPI(prim).GetDirectBindingRel().GetTargets()):
                    omni.kit.commands.execute('BindMaterial',prim_path=[str(prim_path)],material_path=Sdf.Path(mtlpath),strength='weakerThanDescendants')
            if inputimage != None and isimage and self._texture_field.get_value_as_string() != inputimage.Get().path:
                inputimage.Set(Sdf.AssetPath(self._texture_field.get_value_as_string()))
            if inputimage != None and isimage:
                self._show_preview(self._cb_preview.model.get_value_as_bool())
        else:
            print("ERROR: File missing ",os.path.abspath(mdlfile))
# 
# UI Defs and methods
# 
    def _build_ui(self):
        with self.frame:
            with ui.ScrollingFrame(horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON):
                with ui.VStack(height=0):
                    with ui.VStack(spacing=5, name='frame_v_stack'):
                        self.COMBO_CAMS = self._create_combo('Cameras:', self.CAMS_LIST, 0)
                        self.COMBO_CAMS.set_mouse_pressed_fn(lambda a,b,c,d:self._fill_combo(self.COMBO_CAMS))
                        self.COMBO_CAMS.model.get_item_value_model().add_value_changed_fn(lambda a: self._fill_ui(self._get_backplate()))
                        self._texture_field = self._create_path(str='Image:',paths='')
                        self._image_stack = ui.HStack(height=0)
                        with self._image_stack:
                            self._image = ui.Image('',alignment=ui.Alignment.CENTER,fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                        with ui.HStack():
                            ui.Label('Distance:', name='distLbl', width=self.LABEL_WIDTH)
                            self._distance_field = ui.FloatField(width=50)
                            ui.Spacer(width=5.0)
                            self._distance_slider = ui.FloatSlider(min=2, max=1000, step=1.0)
                            # Link field and slider
                            self._distance_slider.model = self._distance_field.model
                            self._distance_slider.model.set_value(200.0)
                            self._distance_field.model.add_value_changed_fn(lambda a: self._auto_create(do=self._cb_create.model.get_value_as_bool(),max=a.get_value_as_float()))
                        with ui.ZStack(height=240):
                            ui.Rectangle(style={"background_color":0xFF212121,"border_radius":7.5})
                            with ui.VStack():
                                ui.Spacer(height=25)
                                with ui.ZStack():
                                    with ui.HStack():
                                        ui.Spacer(width=4)
                                        ui.Rectangle(height=211,style={"background_color":0xFF383838,"border_radius":5.0})
                                        ui.Spacer(width=4)
                                    with ui.VStack():
                                        ui.Spacer(height=5)
                                        with ui.HStack():
                                            ui.Spacer(width=10)
                                            with ui.VStack(spacing=5):
                                                with ui.HStack():
                                                    ui.Label('Name Root:', name='nameLbl', width=self.LABEL_WIDTH)
                                                    self._backplate_name = ui.StringField(name='namefield', height=self.BUTTON_SIZE).model
                                                    self._backplate_name.set_value('BackPlate')
                                                self.COMBO_FIT = self._create_combo('Canvas Fill:', ['Fit Height','Fit Width'], 0)
                                                self.COMBO_FIT.model.get_item_value_model().add_value_changed_fn(lambda a:self._auto_create(self._cb_create.model.get_value_as_bool()))
                                                self._cb_create = self._create_checkbox('Auto Create', True, (lambda a:self._auto_create(a.get_value_as_bool())))
                                                self._cb_dblsided = self._create_checkbox('Double Sided', False, (lambda a:self._auto_create(self._cb_create.model.get_value_as_bool())))
                                                self._cb_shadows = self._create_checkbox('Cast Shadows', True, (lambda a:self._auto_create(self._cb_create.model.get_value_as_bool())))
                                                self._cb_secondary = self._create_checkbox('Invisible To Secondary Rays', False, (lambda a:self._auto_create(self._cb_create.model.get_value_as_bool())))
                                                self._cb_preview = self._create_checkbox('Image Preview', True, (lambda a:self._show_preview(a.get_value_as_bool())))
                                                with ui.HStack():
                                                    self.btn_click = ui.Button('Set BackPlate', name='BtnClick', clicked_fn=lambda: self._fill_ui(self._get_backplate(),force=True))
                                                    self.btn_delete = ui.Button('Delete BackPlate', name='DelClick', clicked_fn=lambda: self._del_plane())
                                            ui.Spacer(width=10)
                                        ui.Spacer(width=2.5)
                            with ui.VStack():
                                ui.Spacer(height=5)
                                with ui.HStack():
                                    ui.Spacer(width=10)
                                    ui.Label('BackPlate Options',alignment=ui.Alignment.LEFT_TOP)
    
    def _show_preview(self, value:bool=None):
        if value == None:
            value = self._cb_preview.model.get_value_as_bool()
        if value and os.path.exists(self._texture_field.get_value_as_string()):
            self._image_stack.height = ui.Length(128)
            self._image.source_url = self._texture_field.get_value_as_string()
        else:
            self._image_stack.height = ui.Length(0)
            self._image.source_url = ''

    def _fill_ui(self, prim:Usd.Prim=None, force:bool=False):
        mtl = shaderprim = prim_img = prim_dist = prim_root = prim_canvas = prim_dbl = prim_shdw = prim_secondary = None
        if prim:
            mtl = UsdShade.MaterialBindingAPI(prim).GetDirectBindingRel().GetTargets()
            if len(mtl) > 0:
                shaderprim = self._stage.GetPrimAtPath(str(mtl[0])+'/Shader')
                prim_img = shaderprim.GetAttribute('inputs:emission_image').Get().path
                prim_dist = -prim.GetAttribute('xformOp:translate').Get()[2]
                prim_root = prim.GetName().split('_')[0]
                prim_canvas = prim.GetAttribute('canvas_fill').Get()
                prim_dbl = shaderprim.GetAttribute('inputs:dbl_sided').Get()
                prim_shdw = not prim.GetAttribute('primvars:doNotCastShadows').Get()
                prim_secondary= prim.GetAttribute('primvars:invisibleToSecondaryRays').Get()
                if prim_img != None:
                    self._texture_field.set_value(prim_img)
                if prim_dist != None:
                    self._distance_slider.model.set_value(prim_dist)
                if prim_root != None:
                    self._backplate_name.set_value(prim_root)
                if prim_canvas != None:
                    self.COMBO_FIT.model.get_item_value_model().set_value(prim_canvas)
                if prim_dbl != None:
                    self._cb_dblsided.model.set_value(prim_dbl)
                if prim_shdw != None:
                    self._cb_shadows.model.set_value(prim_shdw)
                if prim_secondary != None:
                    self._cb_secondary.model.set_value(prim_secondary)
                self._auto_create(True)
            else:
                if force:
                    self._auto_create(True)
                else:
                    self._auto_create(self._cb_create.model.get_value_as_bool())
        else:
            if force:
                self._auto_create(True)
            else:
                self._auto_create(self._cb_create.model.get_value_as_bool())

    def _fill_combo(self, combo:ui.ComboBox):
        '''Fill Combo List'''
        # Get the current index of the selected item
        currentIndex = combo.model.get_item_value_model().as_int
        # # Get the current name of the item
        try:
            currentItem = self.CAMS_LIST[currentIndex]
        except IndexError:
            currentItem = 0
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

    def _create_path(self, str:str, paths:str, lbl_name:str='label', str_name:str='path'):
        with ui.HStack(style={'Button':{'margin':0.0}}):
            ui.Label(str, name=lbl_name, width=self.LABEL_WIDTH)
            field = ui.StringField(name=str_name, height=self.BUTTON_SIZE).model
            field.set_value(paths)
            ui.Spacer(width=5.0)
            ui.Button(image_url='resources/icons/folder.png', width=self.BUTTON_SIZE, height=self.BUTTON_SIZE, clicked_fn=lambda: self._texture_file(self._texture_field))
        return field

    def _create_combo(self, str:str, items:list, selected:bool, lbl_name:str='label', cmb_name:str='combo'):
        with ui.HStack():
            ui.Label(str, name=lbl_name, width=self.LABEL_WIDTH)
            combo = ui.ComboBox(selected, name=cmb_name)
            for item in items:
                combo.model.append_child_item(None, ui.SimpleStringModel(item))
        return combo

    def _create_checkbox(self, str:str, checked:bool, fn, lbl_name:str='label', cb_name:str='checkbox'):
        with ui.HStack():
            checkbox = ui.CheckBox(name=cb_name, width=24)
            checkbox.model.set_value(checked)
            ui.Label(str, name=lbl_name)
            checkbox.model.add_value_changed_fn(fn)
        return checkbox
        
    def _fix_path(self, str:str):
        txt = re.split(r'[/\\]',str)
        return '/'.join(txt)

    def _on_filter_files(self, item) -> bool:
        '''Callback to filter the choices of file names in the open or save dialog'''
        if not item or item.is_folder:
            return True
        if self._open_file_dialog.current_filter_option == 0:
            # Show only files with listed extensions
            return item.path.endswith(('.bmp','.dds','.exr','.gif','.hdr','.jpeg','.jpg','.png','.psd','.tga'))
        else:
            # Show All Files (*)
            return True

    def _texture_file(self, field:ui.StringField):
        def _on_click_open(file_name:str, directory_path:str):
            '''Callback executed when the user selects a file in the open file dialog'''
            if file_name != '' and directory_path != None:
                self._file_return = os.path.join(directory_path, file_name)
                self._file_return = self._fix_path(self._file_return)

            if self._file_return:
                field.set_value(self._file_return)
                self._auto_create(True)
                if self._open_file_dialog:
                    self._open_file_dialog.hide()

            if os.path.exists(self._file_return):
                self.btn_click.enabled = True
                ui.set_shade('white')
            else:
                self.btn_click.enabled = False
                ui.set_shade('transparent')

        def _on_click_cancel(file_name:str, directory_path:str):
            field.set_value('')
            self.btn_click.enabled = False
            ui.set_shade('transparent')
            if self._open_file_dialog:
                self._open_file_dialog.hide()

        if self._open_file_dialog:
            self._open_file_dialog.hide()
            self._open_file_dialog.destroy()

        self._open_file_dialog = FilePickerDialog(
            'Open BackPlate File',
            apply_button_label='Open',
            click_apply_handler=lambda f, d: _on_click_open(f, d),
            click_cancel_handler=lambda f, d: _on_click_cancel(f, d),
            item_filter_options= ['Textures (*.bmp,*.dds,*.exr,*.gif,*.hdr,*.jpeg,*.jpg,*.png,*.psd,*.tga)','All Files (*.*)'],
            item_filter_fn=lambda item: self._on_filter_files(item)
        )
        self._open_file_dialog.show()

    def _on_visibility_changed(self, visible:bool):
        if not visible:
            omni.kit.ui.get_editor_menu().set_value(self._menu_path, False)