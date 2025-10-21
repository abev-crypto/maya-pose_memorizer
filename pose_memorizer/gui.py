# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# PoseMemorizer GUI (Maya2018-)
# -----------------------------------------------------------------------------

import os
import traceback
import json
import functools

from maya import cmds
from maya import mel

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya.OpenMayaUI import MQtUtil

from PySide2 import QtCore
from PySide2 import QtWidgets

import pose_memorizer as pomezer
import pose_memorizer.core as pomezer_core
from maya.api import OpenMaya as om2


# -----------------------------------------------------------------------------

WINDOWS_NAME = "PoseMemorizer"


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Callback
class Callback(object):
    """docstring for Callback."""

    def __init__(self, func, *args, **kwargs):
        super(Callback, self).__init__(*args, **kwargs)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        return

    def __call__(self):
        cmds.undoInfo(openChunk=True)
        try:
            return self._func(*self._args, **self._kwargs)
        except:
            traceback.print_exc()
        finally:
            cmds.undoInfo(closeChunk=True)


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
class OptionFile(object):

    FILENAME = "option.json"

    def __init__(self):
        super(OptionFile, self).__init__()
        self.version = pomezer._version
        self.parameter = {}
        self._file_path = self._get_file_path()
        return

    def unify_sep(func):

        @functools.wraps(func)
        def _wrap(*args, **kwargs):

            def unify_path(path):
                sep = os.sep
                if sep == "\\":
                    return path.replace("/", sep)
                else:
                    return path.replace("\\", sep)

            path = func(*args, **kwargs)

            # 修正ポイント: 文字列以外のイテラブルのみリスト変換
            if isinstance(path, str):
                return unify_path(path)
            elif hasattr(path, "__iter__"):
                return [unify_path(p) for p in path]
            else:
                return path

        return _wrap

    def _check_file_path(self):
        dir_path = os.path.dirname(self._file_path)
        if os.path.exists(dir_path) is False:
            os.makedirs(dir_path)
        return

    @unify_sep
    def _get_file_path(self):
        prefs_path = os.path.join(cmds.about(preferences=True), "prefs")
        ui_lang = cmds.about(uiLanguage=True)
        if ui_lang != "en_US":
            prefs_path = os.path.join(prefs_path, ui_lang, "prefs")

        return os.path.join(prefs_path, "scripts", pomezer._config_dir, self.FILENAME)

    def set_parameter(self, parameter):
        self.parameter = parameter
        return

    def load(self):
        # ディレクトリを作っておく（多言語環境の prefs/ja_JP/prefs も含めて）
        self._check_file_path()

        # まだファイルがない初回は None を返す
        if not os.path.exists(self._file_path):
            return None

        # 破損している/空ファイルでも安全に抜ける
        try:
            with open(self._file_path, "r") as f:
                data = json.load(f)
        except Exception:
            return None

        file_version = data.get("version")
        if file_version != self.version:
            return None

        return data


    def save(self):
        data = {"version": self.version}
        data.update(self.parameter)
        self._check_file_path()
        with open(self._file_path, "w") as f:
            json.dump(data, f, indent=4)
        return


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# ScrollWidget
class ScrollWidget(QtWidgets.QScrollArea):

    def __init__(self, parent=None):
        super(ScrollWidget, self).__init__(parent)
        self._parent = parent
        # scroll
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        return


# HorizontalLine
class HorizontalLine(QtWidgets.QFrame):

    def __init__(self, *args, **kwargs):
        super(HorizontalLine, self).__init__(*args, **kwargs)
        self.setFrameShape(QtWidgets.QFrame.HLine)
        return


# -----------------------------------------------------------------------------
# PoseTreeWidget
class PoseTreeWidget(QtWidgets.QTreeWidget):

    itemRightClicked = QtCore.Signal(QtWidgets.QTreeWidgetItem)

    def __init__(self, *args, **kwargs):
        super(PoseTreeWidget, self).__init__(*args, **kwargs)
        self.__press_item = None

        self.setObjectName("pose_tree")
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setUniformRowHeights(True)
        self.setAnimated(True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.viewport().setAcceptDrops(True)
        return

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        self.__press_item = item
        if item is None and event.button() == QtCore.Qt.LeftButton:
            self.clearSelection()
            self.setCurrentIndex(QtCore.QModelIndex())
        super(PoseTreeWidget, self).mousePressEvent(event)
        return

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.pos())
        if event.button() == QtCore.Qt.RightButton:
            if item is not None and item == self.__press_item:
                self.setCurrentItem(item)
                self.itemRightClicked.emit(item)
        self.__press_item = None
        super(PoseTreeWidget, self).mouseReleaseEvent(event)
        return


# -----------------------------------------------------------------------------
# PoseMemorizerDockableWidget
class PoseMemorizerDockableWidget(MayaQWidgetDockableMixin, ScrollWidget):

    MIRRORNAME = ["Left : Right", "left : right", "_L : _R", "_l : _r"]
    MIRRORAXIS = ["X", "Y", "Z"]
    SCENE_FILE_VERSION = 1

    def __init__(self, parent=None):
        super(PoseMemorizerDockableWidget, self).__init__(parent=parent)

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self._is_loading_scene_data = False
        self._warned_scene_unsaved = False

        self.pomezer = pomezer_core.PoseMemorizer()
        self.op_file = OptionFile()

        self.widget = QtWidgets.QWidget(self)
        widget = self.widget

        # layout
        self.layout = QtWidgets.QVBoxLayout(self)
        layout = self.layout
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        button_layout = QtWidgets.QHBoxLayout(self)
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(0, 0, 0, 0)

        mirror_layout = QtWidgets.QHBoxLayout(self)
        mirror_layout.setSpacing(16)
        mirror_layout.setContentsMargins(0, 0, 0, 0)

        check_layout = QtWidgets.QHBoxLayout(self)
        check_layout.setSpacing(16)
        check_layout.setContentsMargins(0, 0, 0, 0)

        # Widget
        self.memorize_button = QtWidgets.QPushButton("Memorize", self)
        memorize_button = self.memorize_button
        memorize_button.clicked.connect(Callback(self._click_memorize))
        memorize_button.setToolTip(
            "Memorize the current selection. The pose name defaults to PoseF_<CurrentFrame> and can be edited."
        )

        self.update_button = QtWidgets.QPushButton("Update", self)
        update_button = self.update_button
        update_button.clicked.connect(self._click_update)

        self.load_button = QtWidgets.QPushButton("Load", self)
        load_button = self.load_button
        load_button.clicked.connect(self._click_load)

        self.delete_button = QtWidgets.QPushButton("Delete", self)
        delete_button = self.delete_button
        delete_button.clicked.connect(self._click_delete)

        self.pose_list = PoseTreeWidget(self)
        pose_list = self.pose_list
        pose_list.itemDoubleClicked.connect(self._edit_item_name)
        pose_list.itemRightClicked.connect(self._right_click_item)
        pose_list.itemChanged.connect(self._tree_item_changed)
        pose_list.model().rowsInserted.connect(self._tree_structure_changed)
        pose_list.model().rowsRemoved.connect(self._tree_structure_changed)
        pose_list.model().rowsMoved.connect(self._tree_structure_changed)

        self.new_folder_button = QtWidgets.QPushButton("New Folder", self)
        new_folder_button = self.new_folder_button
        new_folder_button.clicked.connect(self._click_new_folder)

        self.delete_tmp_button = QtWidgets.QPushButton("DelTMP", self)
        delete_tmp_button = self.delete_tmp_button
        delete_tmp_button.clicked.connect(self._click_delete_tmp)

        self.range_start_spin = QtWidgets.QSpinBox(self)
        range_start_spin = self.range_start_spin
        range_start_spin.setRange(-999999, 999999)
        range_start_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        try:
            range_start_spin.setValue(int(cmds.playbackOptions(min=True, query=True)))
        except Exception:
            range_start_spin.setValue(0)

        self.range_end_spin = QtWidgets.QSpinBox(self)
        range_end_spin = self.range_end_spin
        range_end_spin.setRange(-999999, 999999)
        range_end_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        try:
            range_end_spin.setValue(int(cmds.playbackOptions(max=True, query=True)))
        except Exception:
            range_end_spin.setValue(0)

        self.range_collect_button = QtWidgets.QPushButton("GetTimeRange", self)
        range_collect_button = self.range_collect_button
        range_collect_button.clicked.connect(self._click_collect_time_range)

        self.range_memorize_button = QtWidgets.QPushButton("RangeMemorize", self)
        range_memorize_button = self.range_memorize_button
        range_memorize_button.clicked.connect(Callback(self._click_range_memorize))

        self.mirror_name_combo = QtWidgets.QComboBox(self)
        mirror_name_combo = self.mirror_name_combo
        mirror_name_combo.addItems(self.MIRRORNAME)

        self.mirror_axis_combo = QtWidgets.QComboBox(self)
        mirror_axis_combo = self.mirror_axis_combo
        mirror_axis_combo.addItems(self.MIRRORAXIS)

        self.mirror_check = QtWidgets.QCheckBox("Mirror", self)
        mirror_check = self.mirror_check
        mirror_check.setChecked(True)

        self.setkey_check = QtWidgets.QCheckBox("Set Key", self)
        setkey_check = self.setkey_check
        setkey_check.setChecked(False)
        # setkey_check.setFixedHeight(28)

        self.namespace_check = QtWidgets.QCheckBox("Namespace Match", self)
        namespace_check = self.namespace_check
        namespace_check.setChecked(True)
        # namespace_check.setFixedHeight(28)

        self.apply_button = QtWidgets.QPushButton("Apply", self)
        apply_button = self.apply_button
        apply_button.clicked.connect(Callback(self._click_apply))
        apply_button.setFixedHeight(28)

        folder_layout = QtWidgets.QHBoxLayout(self)
        folder_layout.setSpacing(4)
        folder_layout.setContentsMargins(0, 0, 0, 0)

        range_layout = QtWidgets.QHBoxLayout(self)
        range_layout.setSpacing(4)
        range_layout.setContentsMargins(0, 0, 0, 0)

        button_layout.addWidget(memorize_button, 2)
        button_layout.addWidget(update_button, 2)
        button_layout.addWidget(load_button, 2)
        button_layout.addWidget(delete_button, 1)

        folder_layout.addWidget(new_folder_button)
        folder_layout.addWidget(delete_tmp_button)

        range_layout.addWidget(QtWidgets.QLabel("Start"))
        range_layout.addWidget(range_start_spin)
        range_layout.addWidget(QtWidgets.QLabel("End"))
        range_layout.addWidget(range_end_spin)
        range_layout.addWidget(range_collect_button)
        range_layout.addWidget(range_memorize_button, 2)

        mirror_layout.addWidget(mirror_axis_combo)
        mirror_layout.addWidget(mirror_check)

        check_layout.addWidget(setkey_check)
        check_layout.addWidget(namespace_check)

        layout.addLayout(button_layout)
        layout.addLayout(range_layout)
        layout.addLayout(folder_layout)
        layout.addWidget(pose_list)
        layout.addWidget(mirror_name_combo)
        layout.addLayout(mirror_layout)
        layout.addWidget(HorizontalLine())
        layout.addLayout(check_layout)
        layout.addWidget(HorizontalLine())
        layout.addWidget(apply_button)

        widget.setLayout(layout)
        self.setWidget(widget)

        self._option_load()
        self._load_scene_pose_data()
        QtWidgets.QApplication.instance().aboutToQuit.connect(
            self._option_save, QtCore.Qt.UniqueConnection
            )
        return

    def dockCloseEventTriggered(self):
        self._option_save()
        return

    def _create_folder_item(self, name="New Folder", parent=None, select=True):
        if parent is None:
            item = QtWidgets.QTreeWidgetItem()
            self.pose_list.addTopLevelItem(item)
        else:
            item = QtWidgets.QTreeWidgetItem(parent)
            parent.setExpanded(True)
        item.setText(0, name)
        item.setData(0, QtCore.Qt.UserRole, {"type": "folder"})
        flags = (QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable |
                 QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled |
                 QtCore.Qt.ItemIsDropEnabled)
        item.setFlags(flags)
        if select:
            self.pose_list.setCurrentItem(item)
        return item

    def _add_pose(self, pose_data, display_name=None, parent=None, select=True):
        if display_name is None:
            if len(pose_data) > 0:
                name = list(pose_data.keys())[0]
            else:
                name = "Pose"
        else:
            name = display_name

        if parent is None:
            item = QtWidgets.QTreeWidgetItem()
            self.pose_list.addTopLevelItem(item)
        else:
            item = QtWidgets.QTreeWidgetItem(parent)
            parent.setExpanded(True)

        item.setText(0, name)
        item.setData(0, QtCore.Qt.UserRole, {"type": "pose", "pose": pose_data})
        flags = (QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable |
                 QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled)
        item.setFlags(flags)
        if select:
            self.pose_list.setCurrentItem(item)
        return item

    def _add_range_pose(self, range_data, display_name=None, parent=None, select=True):
        if display_name is None:
            name = "RangePose"
        else:
            name = display_name

        if parent is None:
            item = QtWidgets.QTreeWidgetItem()
            self.pose_list.addTopLevelItem(item)
        else:
            item = QtWidgets.QTreeWidgetItem(parent)
            parent.setExpanded(True)

        item.setText(0, name)
        item.setData(0, QtCore.Qt.UserRole, {"type": "range", "poses": range_data})
        flags = (QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable |
                 QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled)
        item.setFlags(flags)
        if select:
            self.pose_list.setCurrentItem(item)
        return item

    def _get_ui_parameter(self):
        reslut = {}
        reslut["mirror_name"] = self.mirror_name_combo.currentText()
        reslut["mirror_axis"] = self.mirror_axis_combo.currentText()
        reslut["mirror"] = self.mirror_check.isChecked()
        reslut["setkey"] = self.setkey_check.isChecked()
        reslut["namespace"] = self.namespace_check.isChecked()
        return reslut

    def _get_scene_file_path(self):
        try:
            scene_path = cmds.file(query=True, sn=True)
        except Exception:
            scene_path = ""
        return scene_path or ""

    def _get_scene_json_path(self):
        scene_path = self._get_scene_file_path()
        if scene_path == "":
            return None
        base_name, _ = os.path.splitext(scene_path)
        return base_name + "_PoseMemorizer.json"

    def _serialize_pose_data(self, pose_data):
        result = {}
        for node, parameter in (pose_data or {}).items():
            translate = parameter.get("translate") or (0.0, 0.0, 0.0)
            rotate = parameter.get("rotate")
            if isinstance(rotate, om2.MQuaternion):
                rotate_values = [rotate.x, rotate.y, rotate.z, rotate.w]
            elif isinstance(rotate, (list, tuple)) and len(rotate) == 4:
                rotate_values = [float(v) for v in rotate]
            elif rotate is None:
                rotate_values = [0.0, 0.0, 0.0, 1.0]
            else:
                rotate_values = [0.0, 0.0, 0.0, 1.0]
            try:
                translate_values = [float(v) for v in translate]
            except Exception:
                translate_values = [0.0, 0.0, 0.0]
            result[node] = {
                "translate": translate_values,
                "rotate": rotate_values,
            }
        return result

    def _deserialize_pose_data(self, pose_data):
        result = {}
        for node, parameter in (pose_data or {}).items():
            translate = parameter.get("translate") or [0.0, 0.0, 0.0]
            rotate = parameter.get("rotate")
            if isinstance(rotate, (list, tuple)) and len(rotate) == 4:
                try:
                    rotate_qua = om2.MQuaternion(*[float(v) for v in rotate])
                except Exception:
                    rotate_qua = om2.MQuaternion()
            elif isinstance(rotate, om2.MQuaternion):
                rotate_qua = rotate
            else:
                rotate_qua = om2.MQuaternion()
            try:
                translate_tuple = tuple(float(v) for v in translate)
            except Exception:
                translate_tuple = (0.0, 0.0, 0.0)
            result[node] = {
                "translate": translate_tuple,
                "rotate": rotate_qua,
            }
        return result

    def _serialize_tree_item(self, item):
        data = item.data(0, QtCore.Qt.UserRole) or {}
        item_data = {
            "name": item.text(0),
            "type": data.get("type"),
        }
        item_type = item_data.get("type")
        if item_type == "pose":
            item_data["pose"] = self._serialize_pose_data(data.get("pose", {}))
        elif item_type == "range":
            poses = []
            for pose_entry in data.get("poses", []):
                poses.append({
                    "frame": pose_entry.get("frame"),
                    "pose": self._serialize_pose_data(pose_entry.get("pose", {}))
                })
            item_data["poses"] = poses
        children = []
        for index in range(item.childCount()):
            children.append(self._serialize_tree_item(item.child(index)))
        if children:
            item_data["children"] = children
        return item_data

    def _serialize_tree(self):
        items = []
        for index in range(self.pose_list.topLevelItemCount()):
            items.append(self._serialize_tree_item(self.pose_list.topLevelItem(index)))
        return items

    def _restore_tree_item(self, item_data, parent=None):
        item_type = item_data.get("type")
        name = item_data.get("name")
        if item_type == "pose":
            pose_data = self._deserialize_pose_data(item_data.get("pose", {}))
            item = self._add_pose(pose_data, name, parent=parent, select=False)
        elif item_type == "range":
            range_data = []
            for pose_entry in item_data.get("poses", []):
                range_data.append({
                    "frame": pose_entry.get("frame"),
                    "pose": self._deserialize_pose_data(pose_entry.get("pose", {}))
                })
            item = self._add_range_pose(range_data, name, parent=parent, select=False)
        elif item_type == "folder":
            item = self._create_folder_item(name=name or "New Folder", parent=parent, select=False)
        else:
            item = self._create_folder_item(name=name or "New Folder", parent=parent, select=False)

        for child_data in item_data.get("children", []):
            self._restore_tree_item(child_data, parent=item)

        return item

    def _clear_pose_tree(self):
        self.pose_list.clear()
        return

    def _load_scene_pose_data(self, file_path=None):
        if file_path is None:
            file_path = self._get_scene_json_path()
        if not file_path or os.path.exists(file_path) is False:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to load pose JSON: {}".format(file_path))
            return

        if isinstance(payload, dict):
            version = payload.get("version")
            items = payload.get("items")
            if version not in (None, self.SCENE_FILE_VERSION):
                cmds.warning("Unsupported pose JSON version: {}".format(file_path))
                return
        else:
            items = payload

        if not isinstance(items, list):
            cmds.warning("Invalid pose JSON format: {}".format(file_path))
            return

        self._is_loading_scene_data = True
        try:
            self._clear_pose_tree()
            for item_data in items:
                if not isinstance(item_data, dict):
                    continue
                self._restore_tree_item(item_data)
        finally:
            self._is_loading_scene_data = False

        if self._get_scene_json_path() is not None:
            self._save_scene_pose_data()
        return

    def _save_scene_pose_data(self):
        if self._is_loading_scene_data:
            return
        file_path = self._get_scene_json_path()
        if file_path is None:
            if self._warned_scene_unsaved is False:
                cmds.warning("Save the scene to enable pose JSON saving.")
                self._warned_scene_unsaved = True
            return

        self._warned_scene_unsaved = False

        data = {
            "version": self.SCENE_FILE_VERSION,
            "items": self._serialize_tree(),
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            traceback.print_exc()
        return

    def _tree_item_changed(self, *args, **kwargs):
        if self._is_loading_scene_data:
            return
        self._save_scene_pose_data()
        return

    def _tree_structure_changed(self, *args, **kwargs):
        if self._is_loading_scene_data:
            return
        QtCore.QTimer.singleShot(0, self._save_scene_pose_data)
        return

    def _get_sel_item(self):
        return self.pose_list.currentItem()

    def _edit_item_name(self, item, column=None):
        if item is None:
            return
        self.pose_list.editItem(item, 0)
        return

    def _right_click_item(self, item=None):
        if item is None:
            item = self._get_sel_item()
        if item is None:
            return
        data = item.data(0, QtCore.Qt.UserRole) or {}
        if data.get("type") == "pose":
            pose_data = data.get("pose", {})
        elif data.get("type") == "range":
            poses = data.get("poses", [])
            pose_data = poses[0].get("pose", {}) if len(poses) > 0 else {}
        else:
            pose_data = {}
        if len(pose_data) == 0:
            return
        cmds.select(list(pose_data.keys()), replace=True)
        return

    def _get_insert_parent(self):
        current = self.pose_list.currentItem()
        if current is None:
            return None
        data = current.data(0, QtCore.Qt.UserRole) or {}
        if data.get("type") == "folder":
            return current
        parent = current.parent()
        if parent is not None:
            return parent
        return None

    def _remove_item(self, item):
        parent = item.parent()
        if parent is None:
            index = self.pose_list.indexOfTopLevelItem(item)
            self.pose_list.takeTopLevelItem(index)
        else:
            parent.removeChild(item)
        del(item)
        return

    def _click_memorize(self):
        pose_data = self.pomezer.get_pose()
        if len(pose_data) > 0:
            current_frame = cmds.currentTime(query=True)
            parent = self._get_insert_parent()
            if parent is None:
                default_name = "TMPPoseF_{:g}".format(current_frame)
            else:
                default_name = "PoseF_{:g}".format(current_frame)
            item = self._add_pose(pose_data, default_name, parent)
            self._edit_item_name(item)
            self._save_scene_pose_data()
        return

    def _click_update(self):
        item = self._get_sel_item()
        if item is None:
            return
        data = item.data(0, QtCore.Qt.UserRole) or {}
        if data.get("type") != "pose":
            return
        transform = list(data.get("pose", {}).keys())
        pose_data = self.pomezer.get_pose(transform)
        item.setData(0, QtCore.Qt.UserRole, {"type": "pose", "pose": pose_data})
        self._save_scene_pose_data()
        return

    def _click_load(self):
        dialog_dir = None
        scene_json = self._get_scene_json_path()
        if scene_json is not None:
            dialog_dir = os.path.dirname(scene_json)
        if not dialog_dir:
            scene_file = self._get_scene_file_path()
            if scene_file:
                dialog_dir = os.path.dirname(scene_file)
        if not dialog_dir:
            try:
                dialog_dir = cmds.workspace(query=True, rootDirectory=True)
            except Exception:
                dialog_dir = os.path.expanduser("~")

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Pose JSON",
            dialog_dir,
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
        self._load_scene_pose_data(file_path)
        return

    def _click_delete(self):
        item = self._get_sel_item()
        if item is None:
            return
        self._remove_item(item)
        self._save_scene_pose_data()
        return

    def _click_apply(self):
        item = self._get_sel_item()
        if item is None:
            return
        data = item.data(0, QtCore.Qt.UserRole) or {}
        item_type = data.get("type")
        ui_parameter = self._get_ui_parameter()
        mirror_name = ui_parameter["mirror_name"]
        mirror_axis = ui_parameter["mirror_axis"]
        mirror = ui_parameter["mirror"]
        setkey = ui_parameter["setkey"]
        namespace = ui_parameter["namespace"]
        if item_type == "pose":
            pose_data = data.get("pose", {})
            self.pomezer.apply_pose(pose=pose_data,
                                    mirror=mirror,
                                    mirror_name=mirror_name,
                                    mirror_axis=mirror_axis,
                                    setkey=setkey,
                                    namespace=namespace)
        elif item_type == "range":
            range_data = data.get("poses", [])
            if len(range_data) == 0:
                return
            self.pomezer.apply_pose_sequence(poses=range_data,
                                             mirror=mirror,
                                             mirror_name=mirror_name,
                                             mirror_axis=mirror_axis,
                                             namespace=namespace)
        return

    def _click_new_folder(self):
        item = self._create_folder_item()
        self._edit_item_name(item)
        self._save_scene_pose_data()
        return

    def _click_delete_tmp(self):
        count = self.pose_list.topLevelItemCount()
        for index in reversed(range(count)):
            item = self.pose_list.topLevelItem(index)
            data = item.data(0, QtCore.Qt.UserRole) or {}
            if data.get("type") != "folder":
                removed_item = self.pose_list.takeTopLevelItem(index)
                del(removed_item)
        self._save_scene_pose_data()
        return

    def _click_range_memorize(self):
        start_frame = self.range_start_spin.value()
        end_frame = self.range_end_spin.value()
        if end_frame < start_frame:
            start_frame, end_frame = end_frame, start_frame
        pose_range = self.pomezer.get_pose_range(start_frame, end_frame)
        if len(pose_range) == 0:
            return
        parent = self._get_insert_parent()
        if parent is None:
            default_name = "TMPRange_{:g}_{:g}".format(start_frame, end_frame)
        else:
            default_name = "Range_{:g}_{:g}".format(start_frame, end_frame)
        item = self._add_range_pose(pose_range, default_name, parent)
        self._edit_item_name(item)
        self._save_scene_pose_data()
        return

    def _click_collect_time_range(self):
        start_frame = None
        end_frame = None
        try:
            playback_slider = mel.eval("$tmpVar=$gPlayBackSlider;")
            if playback_slider:
                is_range = cmds.timeControl(playback_slider, query=True, rangeVisible=True)
                if is_range:
                    range_values = cmds.timeControl(playback_slider, query=True, rangeArray=True)
                    if range_values and len(range_values) >= 2:
                        start_frame, end_frame = range_values[:2]
        except Exception:
            start_frame = None
            end_frame = None

        if start_frame is None or end_frame is None:
            try:
                start_frame = cmds.playbackOptions(min=True, query=True)
                end_frame = cmds.playbackOptions(max=True, query=True)
            except Exception:
                return

        start_frame = int(round(start_frame))
        end_frame = int(round(end_frame))
        if end_frame < start_frame:
            start_frame, end_frame = end_frame, start_frame
        self.range_start_spin.setValue(start_frame)
        self.range_end_spin.setValue(end_frame)
        return

    def _option_load(self):
        ui_parameter = self.op_file.load()
        if ui_parameter is None:
            return
        self.mirror_name_combo.setCurrentText(ui_parameter["mirror_name"])
        self.mirror_axis_combo.setCurrentText(ui_parameter["mirror_axis"])
        self.mirror_check.setChecked(ui_parameter["mirror"])
        self.setkey_check.setChecked(ui_parameter["setkey"])
        self.namespace_check.setChecked(ui_parameter["namespace"])
        return

    def _option_save(self):
        ui_parameter = self._get_ui_parameter()
        self.op_file.set_parameter(ui_parameter)
        self.op_file.save()
        return


# -----------------------------------------------------------------------------
# PoseMemorizerMainWindow
class PoseMemorizerMainWindow(object):

    HEIGHT = 360
    WIDTH = 320

    _windows_name = WINDOWS_NAME
    _windows_title = WINDOWS_NAME

    def __init__(self, restore=False):
        super(PoseMemorizerMainWindow, self).__init__()
        self.name = self._windows_name.replace(" ", "_").lower()
        self.workspace_name = "{}WorkspaceControl".format(self.name)

        self.widget = None

        # Restore
        if restore is True:
            self._make_widget()
            # Restore parent
            mixinPtr = MQtUtil.findControl(self.name)
            wks = MQtUtil.findControl(self.workspace_name)
            MQtUtil.addWidgetToMayaLayout(mixinPtr, wks)

        # Create New Workspace
        else:
            self._check_workspase()
            self._make_widget()

        self._set_stylesheet()
        return

    def _check_workspase(self):
        wks = MQtUtil.findControl(self.workspace_name)
        if wks is not None:
            self.close()
        return

    def _set_stylesheet(self):
        try:
            styleFile = os.path.join(os.path.dirname(__file__), "style.css")
            with open(styleFile, "r") as f:
                style = f.read()
        except IOError:
            style = ""

        self.widget.setStyleSheet(style)
        return

    def _resize(self, height, width):
        workspace_name = self.workspace_name
        cmds.workspaceControl(workspace_name, edit=True, resizeHeight=height)
        cmds.workspaceControl(workspace_name, edit=True, resizeWidth=width)
        return

    def _make_uiscript(self):
        reslut = ("from pose_memorizer import gui;"
                  "pomezer_ui=gui.{classname}(restore=True)")

        class_name = self.__class__.__name__
        return reslut.format(classname=class_name)

    def _make_close_command(self):
        return "deleteUI {};".format(self.workspace_name)

    def _make_widget(self):
        self.widget = PoseMemorizerDockableWidget()
        self.widget.setObjectName(self.name)
        return

    def close(self):
        # Mel Command
        cmd = self._make_close_command()
        mel.eval(cmd)
        return

    def show(self):
        widget = self.widget
        uiscript = self._make_uiscript()

        # Show Workspace & Set uiscript
        widget.show(dockable=True, uiScript=uiscript, retain=False)
        # Resize Workspace
        self._resize(self.HEIGHT, self.WIDTH)
        # Set Windows Title
        widget.setWindowTitle(self._windows_title)
        return


# -----------------------------------------------------------------------------
def main():
    # show gui
    pomezer_window = PoseMemorizerMainWindow()
    pomezer_window.show()
    return


if __name__ == '__main__':
    main()


# -----------------------------------------------------------------------------
# EOF
# -----------------------------------------------------------------------------
