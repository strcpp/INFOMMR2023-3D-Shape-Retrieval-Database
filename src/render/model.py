import moderngl
from render.mesh import Mesh
import numpy as np
from typing import Optional
from light import Light
from pyrr import Quaternion, Vector3, Matrix44
from render.shaders import Shaders
from trimesh import Trimesh


class Model:
    """
    Represents a 3D model.
    """
    def __init__(self, app, mesh_name: str, mesh: Trimesh | None = None) -> None:
        """
        Constructor.
        :param app: Glw app.
        :param mesh_name: Name of the model's mesh.
        :param mesh: Model's mesh.
        """
        meshes = Mesh.instance(app)
        programs = Shaders.instance()
        self.prog = programs.get('base-flat')
        self.app = app
    
        if mesh is not None:
            self.mesh = mesh
            new_vao = meshes.trimesh_to_vao(mesh, self.prog)
            self.command = (new_vao, None)
        else:
            self.command = meshes.data[mesh_name]

        self.translation = Vector3()
        self.rotation = Quaternion()
        self.scale = Vector3([1.0, 1.0, 1.0])

        self.show_model = True

        self.model_transformation = Matrix44.identity()
        self.color = [0, 0, 0]

    def update(self, dt: float, interpolation_method: str) -> None:
        pass

    def get_mesh(self):
        """
        Returns the stored trimesh instance
        """
        return self.mesh

    def set_color(self, color: list[int]) -> None:
        """
        Sets model's color.
        :param color: Model color.
        """
        self.color = color

    def move(self, dx: float, dz: float) -> None:
        """
        Moves the model on the x and z axes.
        :param dx: Amount of translation on the x-axis.
        :param dz: Amount of translation on the z-axis.
        """
        self.translation += Vector3([dx, 0, dz])
        self.calculate_model_matrix()

    def translate(self, dx: float, dz: float) -> None:
        """
        Translates the model on the x and z axes once.
        :param dx: Amount of translation on the x-axis.
        :param dz: Amount of translation on the z-axis.
        """
        self.translation = Vector3([dx, 0, dz])
        self.calculate_model_matrix()

    def rotate_y(self, d: float) -> None:
        """
        Rotates the model.
        :param d: Amount of rotation.
        """
        self.rotation = Quaternion.from_y_rotation(d) * self.rotation
        self.calculate_model_matrix()

    def calculate_model_matrix(self) -> None:
        """
        Calculates the model's transformation matrix.
        """
        trans = Matrix44.from_translation(self.translation)
        rot = Matrix44.from_quaternion(Quaternion(self.rotation))
        scale = Matrix44.from_scale(self.scale)
        self.model_transformation = trans * rot * scale

    def get_model_matrix(self) -> np.ndarray:
        """
        Returns the matrix of the model.
        :return: Model matrix.
        """
        model = self.model_transformation
        return np.array(model, dtype='f4')

    def draw(self, proj_matrix: Matrix44, view_matrix: Matrix44, light: Light,) -> None:
        """
        Draws a 3D model.
        :param proj_matrix: Projection matrix.
        :param view_matrix: View matrix.
        :param light: Scene light.
        """
        command = self.command
        texture, vao = command[1], command[0]

        prog = self.prog
        prog['light.Ia'].write(light.Ia)
        prog['light.Id'].write(light.Id)
        prog['light.Is'].write(light.Is)
        prog['light.position'].write(light.position)
        prog['camPos'].write(np.array(self.app.camera.position, dtype='f4'))

        prog['model'].write(self.get_model_matrix())
        prog['view'].write(view_matrix)
        prog['projection'].write(proj_matrix)
        prog['ucolor'].write(np.array(self.color, dtype='f4'))

        if texture is not None:
            texture.use()

        vao.render()
