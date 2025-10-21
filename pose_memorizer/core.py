# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# PoseMemorizer Core (Maya2018-)
# -----------------------------------------------------------------------------

from math import degrees
from math import radians

from maya import cmds
from maya import mel
from maya.api import OpenMaya as om2


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
class PoseMemorizer(object):

    def __init__(self):
        super(PoseMemorizer, self).__init__()
        self.mirror_matrix = self._make_mirror_matrix()
        return

    def _convert_quaternion(self, rotate, order):
        rot = om2.MEulerRotation([radians(r) for r in rotate], order)
        return rot.asQuaternion()

    def _make_mirror_matrix(self):
        x_trans = (-1, 1, 1)
        y_trans = (1, -1, 1)
        z_trans = (1, 1, -1)
        x_qua = (-1, 1, 1, -1)
        y_qua = (1, -1, 1, -1)
        z_qua = (1, 1, -1, -1)
        return {"x": (x_trans, x_qua), "y": (y_trans, y_qua), "z": (z_trans, z_qua)}

    def _make_pose_parameter(self, nodes):

        def get_transform(node):
            return cmds.getAttr("{}.translate".format(node))[0]

        def get_quaternion(node):
            conv_qua = self._convert_quaternion
            order = cmds.getAttr("{}.rotateOrder".format(node))
            rotate = conv_qua(cmds.getAttr("{}.rotate".format(node))[0], order)
            axis = conv_qua(cmds.getAttr("{}.rotateAxis".format(node))[0], order)
            orient = om2.MQuaternion()
            if cmds.attributeQuery("jointOrient", node=node, exists=True) is True:
                orient = conv_qua(cmds.getAttr("{}.jointOrient".format(node))[0], order)
            return axis * rotate * orient

        return {n: {"translate": get_transform(n), "rotate": get_quaternion(n)}
                for n in nodes}

    def _convert_target_pose(self, pose, mirror, mirror_name, namespace):

        def basename(name):
            return name.split(":")[-1]

        if mirror is True:
            split_name = mirror_name.split(" : ")
            left = split_name[0]
            right = split_name[1]
            change_pose = {}
            for n, m in pose.items():
                if left in n:
                    change_pose[n.replace(left, right)] = m
                elif right in n:
                    change_pose[n.replace(right, left)] = m
                else:
                    change_pose[n] = m
            pose = change_pose

        target_pose = {}
        sel_transforms = self._get_sel_transform()
        if sel_transforms:
            if namespace is True:
                sel_trans = set(sel_transforms)
                target_pose = {n: m for n, m in pose.items() if n in sel_trans}
            else:
                sel_trans = {basename(t): t for t in sel_transforms}
                target_pose = {sel_trans.get(basename(n)): m for n, m in pose.items()
                               if sel_trans.get(basename(n)) is not None}
            return target_pose

        if namespace is True:
            target_pose = {n: m for n, m in pose.items() if cmds.objExists(n)}
        else:
            pose_by_basename = {}
            for node_name, parameter in pose.items():
                pose_by_basename.setdefault(basename(node_name), parameter)

            target_pose = {}
            for node in cmds.ls(type="transform") or []:
                pose_parameter = pose_by_basename.get(basename(node))
                if pose_parameter is not None:
                    target_pose[node] = pose_parameter
        return target_pose

    def _get_sel_transform(self):
        return cmds.ls(selection=True, transforms=True)

    def _get_mirror_matrix(self, mirror_axis):
        return self.mirror_matrix.get(mirror_axis.lower())

    def _get_translate_rotate(self, pose, mirror, mirror_axis):

        def convert_matrix(node, parameter):
            conv_qua = self._convert_quaternion
            translate = parameter.get("translate")
            rot_qua = parameter.get("rotate")
            order = cmds.getAttr("{}.rotateOrder".format(node))
            inv_axis = conv_qua(cmds.getAttr("{}.rotateAxis".format(node))[0], order).inverse()
            inv_orient = om2.MQuaternion()
            if cmds.attributeQuery("jointOrient", node=node, exists=True) is True:
                inv_orient = conv_qua(cmds.getAttr("{}.jointOrient".format(node))[0], order).inverse()
            rotate = (inv_axis * rot_qua * inv_orient).asEulerRotation()
            return (tuple(translate), tuple(degrees(r) for r in rotate))

        def convert_mirror_matrix(node, parameter, mirror_trans, mirror_qua):
            conv_qua = self._convert_quaternion
            src_translate = parameter.get("translate")
            src_rotate = parameter.get("rotate")
            order = cmds.getAttr("{}.rotateOrder".format(node))
            inv_axis = conv_qua(cmds.getAttr("{}.rotateAxis".format(node))[0], order).inverse()
            inv_orient = om2.MQuaternion()
            if cmds.attributeQuery("jointOrient", node=node, exists=True) is True:
                inv_orient = conv_qua(cmds.getAttr("{}.jointOrient".format(node))[0], order).inverse()
            translate = [s * m for s, m in zip(src_translate, mirror_trans)]
            mirror_rot = om2.MQuaternion([s * m for s, m in zip(src_rotate, mirror_qua)])
            rotate = (inv_axis * mirror_rot * inv_orient).asEulerRotation()
            return (tuple(translate), tuple(degrees(r) for r in rotate))

        # main
        if mirror is True:
            mirror_trans, mirror_qua = self._get_mirror_matrix(mirror_axis)
            return {n: convert_mirror_matrix(n, m, mirror_trans, mirror_qua)
                    for n, m in pose.items()}
        else:
            return {n: convert_matrix(n, p) for n, p in pose.items()}

    def _get_setkey_command(self, trans_rot):
        tx_cmd = "setKeyframe -at tx -v {value} -dd true {node}"
        ty_cmd = "setKeyframe -at ty -v {value} -dd true {node}"
        tz_cmd = "setKeyframe -at tz -v {value} -dd true {node}"
        rx_cmd = "setKeyframe -at rx -v {value} -dd true {node}"
        ry_cmd = "setKeyframe -at ry -v {value} -dd true {node}"
        rz_cmd = "setKeyframe -at rz -v {value} -dd true {node}"

        reslut = []
        reslut_add = reslut.append

        for n, m in trans_rot.items():
            translate, rotate = m
            if cmds.getAttr("{}.translateX".format(n), lock=True) is False:
                reslut_add(tx_cmd.format(node=n, value=translate[0]))
            if cmds.getAttr("{}.translateY".format(n), lock=True) is False:
                reslut_add(ty_cmd.format(node=n, value=translate[1]))
            if cmds.getAttr("{}.translateZ".format(n), lock=True) is False:
                reslut_add(tz_cmd.format(node=n, value=translate[2]))
            if cmds.getAttr("{}.rotateX".format(n), lock=True) is False:
                reslut_add(rx_cmd.format(node=n, value=rotate[0]))
            if cmds.getAttr("{}.rotateY".format(n), lock=True) is False:
                reslut_add(ry_cmd.format(node=n, value=rotate[1]))
            if cmds.getAttr("{}.rotateZ".format(n), lock=True) is False:
                reslut_add(rz_cmd.format(node=n, value=rotate[2]))

        # DG Dirty
        nodes = " ".join(trans_rot.keys())
        reslut_add("dgdirty {}".format(nodes))
        return ";".join(reslut)

    def _get_setattr_command(self, trans_rot):
        tx_cmd = "setAttr {node}.tx {value}"
        ty_cmd = "setAttr {node}.ty {value}"
        tz_cmd = "setAttr {node}.tz {value}"
        rx_cmd = "setAttr {node}.rx {value}"
        ry_cmd = "setAttr {node}.ry {value}"
        rz_cmd = "setAttr {node}.rz {value}"

        reslut = []
        reslut_add = reslut.append

        for n, m in trans_rot.items():
            translate, rotate = m
            if cmds.getAttr("{}.translateX".format(n), lock=True) is False:
                reslut_add(tx_cmd.format(node=n, value=translate[0]))
            if cmds.getAttr("{}.translateY".format(n), lock=True) is False:
                reslut_add(ty_cmd.format(node=n, value=translate[1]))
            if cmds.getAttr("{}.translateZ".format(n), lock=True) is False:
                reslut_add(tz_cmd.format(node=n, value=translate[2]))
            if cmds.getAttr("{}.rotateX".format(n), lock=True) is False:
                reslut_add(rx_cmd.format(node=n, value=rotate[0]))
            if cmds.getAttr("{}.rotateY".format(n), lock=True) is False:
                reslut_add(ry_cmd.format(node=n, value=rotate[1]))
            if cmds.getAttr("{}.rotateZ".format(n), lock=True) is False:
                reslut_add(rz_cmd.format(node=n, value=rotate[2]))

        # DG Dirty
        nodes = " ".join(trans_rot.keys())
        reslut_add("dgdirty {}".format(nodes))
        return ";".join(reslut)

    def get_pose(self, transform=[]):
        if len(transform) == 0:
            transform = self._get_sel_transform()
        return self._make_pose_parameter(transform)

    def get_pose_range(self, start_frame, end_frame, transform=None):
        if transform is None or len(transform) == 0:
            transform = self._get_sel_transform()
        if transform is None or len(transform) == 0:
            return []

        try:
            key_times = cmds.keyframe(transform, time=(start_frame, end_frame), query=True)
        except Exception:
            return []
        if key_times is None:
            return []

        frames = sorted(set(key_times))
        if len(frames) == 0:
            return []

        current_time = cmds.currentTime(query=True)
        poses = []
        cmds.refresh(suspend=True)
        try:
            for frame in frames:
                cmds.currentTime(frame, edit=True)
                pose = self._make_pose_parameter(transform)
                poses.append({"frame": frame, "pose": pose})
        finally:
            cmds.currentTime(current_time, edit=True)
            cmds.refresh(suspend=False)
            cmds.refresh(currentView=True)
        return poses

    def apply_pose(self, pose, mirror, mirror_name, mirror_axis, setkey, namespace):
        cmds.refresh(suspend=True)
        try:
            target_pose = self._convert_target_pose(pose, mirror, mirror_name, namespace)
            pose_tr = self._get_translate_rotate(target_pose, mirror, mirror_axis)
            cmd = ""
            if setkey is True:
                cmd = self._get_setkey_command(pose_tr)
            else:
                cmd = self._get_setattr_command(pose_tr)
            if cmd:
                mel.eval(cmd)
        finally:
            cmds.refresh(suspend=False)
            cmds.refresh(currentView=True)
        return

    def apply_pose_sequence(self, poses, mirror, mirror_name, mirror_axis, namespace):
        if poses is None or len(poses) == 0:
            return

        current_time = cmds.currentTime(query=True)
        cmds.refresh(suspend=True)
        try:
            for pose_data in sorted(poses, key=lambda x: x.get("frame", 0)):
                frame = pose_data.get("frame")
                pose = pose_data.get("pose")
                if pose is None or len(pose) == 0:
                    continue
                if frame is not None:
                    cmds.currentTime(frame, edit=True)
                target_pose = self._convert_target_pose(pose, mirror, mirror_name, namespace)
                pose_tr = self._get_translate_rotate(target_pose, mirror, mirror_axis)
                if len(pose_tr) == 0:
                    continue
                cmd = self._get_setkey_command(pose_tr)
                if cmd:
                    mel.eval(cmd)
        finally:
            cmds.currentTime(current_time, edit=True)
            cmds.refresh(suspend=False)
            cmds.refresh(currentView=True)
        return


# -----------------------------------------------------------------------------
# EOF
# -----------------------------------------------------------------------------
