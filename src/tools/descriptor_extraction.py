import numpy as np
from numba import njit
import matplotlib.pyplot as plt
import os
import pandas as pd
from trimesh import Trimesh


output_dir1 = "tools/outputs/histograms/descriptors"
output_dir2 = "src/tools/outputs/histograms/descriptors"

np.random.seed(42)

SAMPLE_SIZE = 100
BIN_SIZE = 10


def calculate_mesh_volume(mesh: Trimesh) -> float:
    """
    Calculates the volume of a mesh.
    :param mesh: Trimesh mesh.
    :return: Volume of the mesh.
    """
    # Check if the mesh is watertight after repair
    if not mesh.is_watertight:
        mesh.fill_holes()

    # Calculate the volume using the watertight mesh
    reference_point = mesh.centroid
    volumes = []
    for face in mesh.faces:
        v0, v1, v2 = mesh.vertices[face]
        tetra_volume = np.dot(reference_point - v0, np.cross(v1 - v0, v2 - v0)) / 6.0
        volumes.append(tetra_volume)

    volume = np.abs(sum(volumes))
    return volume


class ShapeDescriptors:
    """
    Represents the descriptors of a shape.
    """
    def __init__(self, mesh, model_class, model_name, surface_area, compactness, rectangularity, diameter, convexity,
                 eccentricity, A3, D1, D2, D3, D4):
        """
        Constructor
        """
        self.mesh = mesh
        self.n_vertices = len(mesh.vertices)
        self.n_faces = len(mesh.faces)
        self.model_class = model_class
        self.model_name = model_name
        self.surface_area = surface_area
        self.surface_area_normalized = surface_area
        self.compactness = compactness
        self.compactness_normalized = compactness
        self.rectangularity = rectangularity
        self.rectangularity_normalized = rectangularity
        self.diameter = diameter
        self.diameter_normalized = diameter
        self.convexity = convexity
        self.convexity_normalized = convexity
        self.eccentricity = eccentricity
        self.eccentricity_normalized = eccentricity
        self.A3 = A3
        self.D1 = D1
        self.D2 = D2
        self.D3 = D3
        self.D4 = D4
        self.sample_size = SAMPLE_SIZE
        self.bin_size = BIN_SIZE

    @classmethod
    def from_csv_row(cls, row, mesh):
        model_class = row['Model Class'].item()

        model_name = row['Model Name'].item()

        surface_area = row['Surface Area'].iloc[0] if not pd.isnull(row['Surface Area'].iloc[0]) else 0.0

        compactness = row['Compactness'].iloc[0] if not pd.isnull(row['Compactness'].iloc[0]) else 0.0
        rectangularity = row['Rectangularity'].iloc[0] if not pd.isnull(row['Rectangularity'].iloc[0]) else 0.0
        diameter = row['Diameter'].iloc[0] if not pd.isnull(row['Diameter'].iloc[0]) else 0.0
        convexity = row['Convexity'].iloc[0] if not pd.isnull(row['Convexity'].iloc[0]) else 0.0
        eccentricity = row['Eccentricity'].iloc[0] if not pd.isnull(row['Eccentricity'].iloc[0]) else 0.0

        A3 = [float(num) for num in row['A3'].values[0][1:-1].split(', ')]
        D1 = [float(num) for num in row['D1'].values[0][1:-1].split(', ')]
        D2 = [float(num) for num in row['D2'].values[0][1:-1].split(', ')]
        D3 = [float(num) for num in row['D3'].values[0][1:-1].split(', ')]
        D4 = [float(num) for num in row['D4'].values[0][1:-1].split(', ')]

        return cls(
            mesh=mesh,
            model_class=model_class,
            model_name=model_name,
            surface_area=surface_area,
            compactness=compactness,
            rectangularity=rectangularity,
            diameter=diameter,
            convexity=convexity,
            eccentricity=eccentricity,
            A3=A3,
            D1=D1,
            D2=D2,
            D3=D3,
            D4=D4)

    @classmethod
    def from_mesh(cls, mesh, model_class, model_name):
        """
        2nd Constructor.
        """
        model_name, _ = os.path.splitext(model_name)
        surface_area = mesh.area

        volume = calculate_mesh_volume(mesh)

        compactness = cls.compute_compactness(mesh, volume)
        rectangularity = cls.compute_rectangularity(mesh, volume)
        diameter = cls.compute_diameter(mesh.convex_hull.vertices)
        convexity = cls.compute_convexity(mesh, volume)
        eccentricity = cls.compute_eccentricity(mesh)
        A3 = cls.compute_A3(mesh, SAMPLE_SIZE)
        D1 = cls.compute_D1(mesh, SAMPLE_SIZE)
        D2 = cls.compute_D2(mesh, SAMPLE_SIZE)
        D3 = cls.compute_D3(mesh, SAMPLE_SIZE)
        D4 = cls.compute_D4(mesh, SAMPLE_SIZE)

        return cls(
            mesh=mesh,
            model_class=model_class,
            model_name=model_name,
            surface_area=surface_area,
            compactness=compactness,
            rectangularity=rectangularity,
            diameter=diameter,
            convexity=convexity,
            eccentricity=eccentricity,
            A3=A3,
            D1=D1,
            D2=D2,
            D3=D3,
            D4=D4
        )

    def compute_compactness(mesh, volume: float) -> float:
        """
        Calculate mesh compactness.
        :param volume: Mesh volume.
        :return: Mesh compactness.
        """
        V = volume
        A = mesh.area
        return (A ** 3) / (V ** 2)

    def compute_rectangularity(mesh, volume: float) -> float:
        """
        Calculates the mesh rectangularity.
        :param volume: Mesh volume.
        :return: Mesh rectangulariy.
        """
        obb_volume = mesh.bounding_box_oriented.volume
        return volume / obb_volume

    @staticmethod
    @njit
    def compute_diameter(vertices: np.ndarray) -> float:
        """
        Calculates the mesh diameter.
        :param vertices: Mesh vertices.
        :return: Mesh diameter.
        """
        diameter = 0
        for i in range(len(vertices)):
            for j in range(i + 1, len(vertices)):
                dist = np.linalg.norm(vertices[i] - vertices[j])
                diameter = max(diameter, dist)
        return diameter

    def compute_convexity(mesh, volume: float) -> float:
        """
        Calculates the mesh convexity.
        :param volume: Mesh volume.
        :return: Mesh convexity.
        """
        return volume / mesh.convex_hull.volume

    def compute_eccentricity(mesh) -> float:
        """
        Calculates the mesh eccentricity.
        :return: Mesh eccentricity.
        """
        covariance_matrix = np.cov(np.transpose(mesh.vertices))
        eigenvalues = np.linalg.eigvals(covariance_matrix)
        return max(eigenvalues) / min(eigenvalues)

    def compute_A3(mesh, num_samples: int) -> float:
        """
        Calculates the A3 descriptor.
        :param num_samples: Number of random samples to use.
        :return: A3 descriptor.
        """
        angles = []
        vertices = mesh.vertices
        for _ in range(num_samples):
            A, B, C = vertices[np.random.choice(vertices.shape[0], 3, replace=False)]
            BA = A - B
            BC = C - B
            cosine_angle = np.dot(BA, BC) / (np.linalg.norm(BA) * np.linalg.norm(BC))
            angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
            angles.append(angle)

        histogram, bin_edges = np.histogram(angles, bins=BIN_SIZE, range=(0, np.pi))
        a3 = [x / np.sum(histogram) for x in histogram]
        return a3

    def save_A3_histogram_image(self) -> None:
        """
        Saves the histogram of the A3 descriptor.
        """
        histogram = self.A3

        fig, ax = plt.subplots(figsize=(10, 6))
        bin_edges = np.linspace(0, np.pi, len(histogram) + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        ax.bar(bin_centers, histogram, width=np.pi / len(histogram), align='center', edgecolor='black')
        ax.set_xlabel('Angle (radians)')
        ax.set_ylabel('Frequency')
        ax.set_title('Angle Between 3 Random Vertices')
        ax.set_xlim(0, np.pi)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()

        # Save the figure directly to the desired path
        filename = f"A3_{self.model_class}_{self.model_name}.png"

        try:
            output_path = os.path.join(output_dir1, filename)
        except FileNotFoundError:
            output_path = os.path.join(output_dir2, filename)

        plt.savefig(output_path, format="png")
        plt.close(fig)

    def compute_D1(mesh, num_samples: int) -> float:
        """
        Calculates the D1 descriptor.
        :param num_samples: Number of random samples to use.
        :return: D1 descriptor.
        """
        barycenter = mesh.centroid

        distances = []
        vertices = mesh.vertices
        for _ in range(num_samples):
            # Sample a random vertex
            vertex = vertices[np.random.choice(vertices.shape[0])]
            # Compute the distance
            distance = np.linalg.norm(vertex - barycenter)
            distances.append(distance)
        histogram, bin_edges = np.histogram(distances, bins=BIN_SIZE)
        d1 = [x / np.sum(histogram) for x in histogram]
        return d1

    def save_D1_histogram_image(self) -> None:
        """
        Saves the histogram of the D1 descriptor.
        """
        histogram = self.D1

        fig, ax = plt.subplots(figsize=(10, 6))
        bin_edges = np.linspace(0, np.pi, len(histogram) + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        ax.bar(bin_centers, histogram, width=np.pi / len(histogram), align='center', edgecolor='black')
        ax.set_xlabel('Distance')
        ax.set_ylabel('Frequency')
        ax.set_title('Distance Between Barycenter and Eandom Vertex')
        ax.set_xlim(0, np.pi)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()

        # Save the figure directly to the desired path
        filename = f"D1_{self.model_class}_{self.model_name}.png"
        try:
            output_path = os.path.join(output_dir1, filename)
        except FileNotFoundError:
            output_path = os.path.join(output_dir2, filename)
        plt.savefig(output_path, format="png")
        plt.close(fig)

    def compute_D2(mesh, num_samples: int) -> float:
        """
        Calculates the D2 descriptor.
        :param num_samples: Number of random samples to use.
        :return: D2 descriptor.
        """
        distances = []
        vertices = mesh.vertices
        for _ in range(num_samples):
            # Sample two distinct random vertices
            vertex1, vertex2 = vertices[np.random.choice(vertices.shape[0], 2, replace=False)]

            # Compute the distance
            distance = np.linalg.norm(vertex1 - vertex2)
            distances.append(distance)
        histogram, bin_edges = np.histogram(distances, bins=BIN_SIZE)
        d2 = [x / np.sum(histogram) for x in histogram]
        return d2

    def save_D2_histogram_image(self) -> None:
        """
        Saves the histogram of the D2 descriptor.
        """
        histogram = self.D2

        fig, ax = plt.subplots(figsize=(10, 6))
        bin_edges = np.linspace(0, np.pi, len(histogram) + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        ax.bar(bin_centers, histogram, width=np.pi / len(histogram), align='center', edgecolor='black')
        ax.set_xlabel('Distance')
        ax.set_ylabel('Frequency')
        ax.set_title('Distance Between 2 Random Vertices')
        ax.set_xlim(0, np.pi)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()

        # Save the figure directly to the desired path
        filename = f"D2_{self.model_class}_{self.model_name}.png"
        try:
            output_path = os.path.join(output_dir1, filename)
        except FileNotFoundError:
            output_path = os.path.join(output_dir2, filename)
        plt.savefig(output_path, format="png")
        plt.close(fig)

    def compute_D3(mesh, num_samples: int) -> float:
        """
        Calculates the D3 descriptor.
        :param num_samples: Number of random samples to use.
        :return: D3 descriptor.
        """
        areas = []
        vertices = mesh.vertices
        for _ in range(num_samples):
            # Sample three distinct random vertices
            A, B, C = vertices[np.random.choice(vertices.shape[0], 3, replace=False)]

            # Compute the lengths of the sides of the triangle
            a = round(np.linalg.norm(B - C), 3)
            b = round(np.linalg.norm(A - C), 3)
            c = round(np.linalg.norm(A - B), 3)

            # Compute the semi-perimeter
            s = round(((a + b + c) / 2), 3)

            # Compute the area using Heron's formula
            area = round(np.sqrt(np.abs(s * (s - a) * (s - b) * (s - c))), 3)
            areas.append(np.sqrt(area))
            try:
                histogram, bin_edges = np.histogram(areas, bins=BIN_SIZE)
            except ValueError:
                raise ValueError
        d3 = [x / np.sum(histogram) for x in histogram]
        return d3

    def save_D3_histogram_image(self) -> None:
        """
        Saves the histogram of the D3 descriptor.
        """
        histogram = self.D3

        fig, ax = plt.subplots(figsize=(10, 6))
        bin_edges = np.linspace(0, np.pi, len(histogram) + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        ax.bar(bin_centers, histogram, width=np.pi / len(histogram), align='center', edgecolor='black')
        ax.set_xlabel('Square Root of Area')
        ax.set_ylabel('Frequency')
        ax.set_title('Square Root of Area of Triangle Given by 3 Random Vertices')
        ax.set_xlim(0, np.pi)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()

        # Save the figure directly to the desired path
        filename = f"D3_{self.model_class}_{self.model_name}.png"
        try:
            output_path = os.path.join(output_dir1, filename)
        except FileNotFoundError:
            output_path = os.path.join(output_dir2, filename)
        plt.savefig(output_path, format="png")
        plt.close(fig)

    def compute_D4(mesh, num_samples: int) -> float:
        """
        Calculates the D4 descriptor.
        :param num_samples: Number of random samples to use.
        :return: D4 descriptor.
        """
        volumes = []
        vertices = mesh.vertices
        for _ in range(num_samples):
            # Sample four distinct random vertices
            A, B, C, D = vertices[np.random.choice(vertices.shape[0], 4, replace=False)]

            # Compute the volume of the tetrahedron
            AB = B - A
            AC = C - A
            AD = D - A
            volume = np.abs(np.dot(AB, np.cross(AC, AD))) / 6

            volumes.append(np.cbrt(volume))
        histogram, bin_edges = np.histogram(volumes, bins=BIN_SIZE)
        d4 = [x / np.sum(histogram) for x in histogram]
        return d4

    def save_D4_histogram_image(self) -> None:
        """
        Saves the histogram of the D4 descriptor.
        """
        histogram = self.D4

        fig, ax = plt.subplots(figsize=(10, 6))
        bin_edges = np.linspace(0, np.pi, len(histogram) + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        ax.bar(bin_centers, histogram, width=np.pi / len(histogram), align='center', edgecolor='black')
        ax.set_xlabel('Cube Root of Area')
        ax.set_ylabel('Frequency')
        ax.set_title('Cube Root of Volume of Tetrahedron Formed by 4 Random Vertices')
        ax.set_xlim(0, np.pi)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()

        # Save the figure directly to the desired path
        filename = f"D4_{self.model_class}_{self.model_name}.png"
        try:
            output_path = os.path.join(output_dir1, filename)
        except FileNotFoundError:
            output_path = os.path.join(output_dir2, filename)
        plt.savefig(output_path, format="png")
        plt.close(fig)

    def get_single_features(self) -> list[float]:
        """
        Returns the non-normalized single features.
        :return: Non-normalized single features.
        """
        return [self.surface_area,
                self.compactness,
                self.rectangularity,
                self.diameter,
                self.convexity,
                self.eccentricity]

    def get_weighted_normalized_features(self) -> list[float]:
        """
        Returns the weighted normalized single and histogram features.
        :return: Weighted normalized single and histogram features.
        """
        return_list = [self.surface_area_normalized * 0.015,
                       self.compactness_normalized * 0.015,
                       self.rectangularity_normalized * 0.015,
                       self.diameter_normalized * 0.015,
                       self.convexity_normalized * 0.015,
                       self.eccentricity_normalized * 0.015,
                       ]

        return_list.extend([x * 0.225 for x in self.A3])
        return_list.extend([x * 0.12 for x in self.D1])
        return_list.extend([x * 0.18 for x in self.D2])
        return_list.extend([x * 0.185 for x in self.D3])
        return_list.extend([x * 0.2 for x in self.D4])

        return return_list

    def get_normalized_single_features(self) -> list[float]:
        """
        Returns the normalized single features.
        :return: Normalized single features.
        """
        return [self.surface_area_normalized,
                self.compactness_normalized,
                self.rectangularity_normalized,
                self.diameter_normalized,
                self.convexity_normalized,
                self.eccentricity_normalized,
                ]

    def get_normalized_histogram_features(self) -> list[float]:
        """
        Returns the normalized histogram features.
        :return: Normalized histogram features.
        """
        return_list = []

        return_list.extend([x for x in self.A3])
        return_list.extend([x for x in self.D1])
        return_list.extend([x for x in self.D2])
        return_list.extend([x for x in self.D3])
        return_list.extend([x for x in self.D4])

        return return_list

    def normalize_single_features(self, updated_features: np.ndarray) -> None:
        """
        Normalizes the shape's single features.
        :param updated_features: Normalized single features.
        """
        self.surface_area_normalized = updated_features[0]
        self.compactness_normalized = updated_features[1]
        self.rectangularity_normalized = updated_features[2]
        self.diameter_normalized = updated_features[3]
        self.convexity_normalized = updated_features[4]
        self.eccentricity_normalized = updated_features[5]
