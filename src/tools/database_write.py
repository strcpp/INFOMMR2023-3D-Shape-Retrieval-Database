from __future__ import annotations
import pandas as pd
import trimesh
from descriptor_extraction import *
from display_statistics import return_neighbors
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


database_path = os.path.join('src', 'tools', 'outputs', 'database.csv')
models_path = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'models', 'Default')
normalized_models_path = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'models', 'Normalized')

THRESHOLD = 500


def resample(mesh: trimesh.Trimesh, target_vertices: int) -> trimesh.Trimesh | None:
    """
    Resamples a mesh to a specific target number of vertices.
    :param mesh: Model mesh.
    :param target_vertices: Target vertices to resample to.
    :return: Resampled mesh.
    """
    iterations = 0
    while len(mesh.vertices) > target_vertices + THRESHOLD or len(mesh.vertices) < target_vertices - THRESHOLD:
        # If number of vertices is too high, simplify
        if len(mesh.vertices) > target_vertices + THRESHOLD:
            new_face_count = target_vertices * (len(mesh.faces) / len(mesh.vertices))
            mesh = mesh.simplify_quadratic_decimation(new_face_count)

        # If number of vertices is too low, subdivide
        if len(mesh.vertices) < target_vertices - THRESHOLD:
            mesh = trimesh.Trimesh(*trimesh.remesh.subdivide(mesh.vertices, mesh.faces))
        iterations += 1
        if iterations > 10:
            return None
    return mesh


def align_to_largest_extent_component(mesh: Trimesh) -> Trimesh:
    """
    Aligns mesh to the largest extent component.
    :param mesh: Mesh that will be aligned.
    :return: Aligned mesh.
    """
    extents = mesh.extents
    max_extent_direction = mesh.vertices.max(axis=0) - mesh.vertices.min(axis=0)
    major_axis_index = np.argmax(extents)
    major_axis_sign = np.sign(max_extent_direction[major_axis_index])

    # Ensure the major axis points in the positive direction
    if major_axis_sign < 0:
        mesh.vertices[:, major_axis_index] *= -1  # This flips the mesh along the major axis

    return mesh


def align_mesh_axes(eig_vectors: np.ndarray, eig_values: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    """
    Calculates aligned mesh eigenvectors based on the eigenvalues and the extents of the mesh vertices.
    :param eig_vectors: Mesh eigenvectors.
    :param eig_values: Mesh eigenvalues.
    :param vertices: Mesh vertices.
    :return: Aligned eigenvectors.
    """
    # Sort eigenvalues and eigenvectors by the magnitude of the eigenvalues (major to minor)
    sort_idx = np.argsort(-eig_values)
    eig_vectors = eig_vectors[:, sort_idx]

    # Project the vertices onto the eigenvectors to find their extents
    projected_vertices = vertices @ eig_vectors
    min_extents = projected_vertices.min(axis=0)
    max_extents = projected_vertices.max(axis=0)
    extents = max_extents - min_extents

    # The axis with the largest extent should be aligned with the X-axis
    # The axis with the smallest extent should be aligned with the Y-axis
    axis_order = np.argsort(-extents)  # Sort axes by extent in descending order

    # Create a new set of eigenvectors with the correct order
    aligned_eig_vectors = eig_vectors[:, axis_order]

    # Ensure right-handed coordinate system
    cross_product = np.cross(aligned_eig_vectors[:, 0], aligned_eig_vectors[:, 1])
    if np.dot(cross_product, aligned_eig_vectors[:, 2]) < 0:
        aligned_eig_vectors[:, 2] = -aligned_eig_vectors[:, 2]

    return aligned_eig_vectors


def align_mesh(mesh: Trimesh, eig_vectors: np.ndarray) -> Trimesh:
    """
    Aligns a mesh based on given eigenvectors.
    :param mesh: Mesh.
    :param eig_vectors: Eigenvectors.
    :return: Aligned mesh.
    """
    # Apply the rotation to align the mesh with the new axes
    mesh.vertices = mesh.vertices @ eig_vectors

    # Ensure the axes are pointing in the positive direction based on the vertices' positions
    for i in range(3):
        if mesh.vertices[:, i].mean() < 0:
            mesh.vertices[:, i] = -mesh.vertices[:, i]

    return mesh


def normalize_mesh(args):
    """
    Processes a mesh based on the 5-step normalization process.
    """
    m, target_faces = args
    model_class = m[1]
    model_name = m[2]
    mesh = m[0]

    # Step 1: Resample
    mesh.process()
    mesh.remove_duplicate_faces()
    mesh = resample(mesh, target_faces)

    if mesh:
        # Step 2: Translation
        barycenter = mesh.centroid
        mesh.apply_translation(-barycenter)

        # Step 3: Pose (alignment)
        covariance_matrix = np.cov(mesh.vertices.T)
        eig_values, eig_vectors = np.linalg.eig(covariance_matrix)
        sorted_indices = np.argsort(-eig_values)
        eig_vectors = eig_vectors[:, sorted_indices]
        aligned_eig_vectors = align_mesh_axes(eig_vectors, eig_values, mesh.vertices)
        mesh = align_mesh(mesh, aligned_eig_vectors)

        # Step 4: Scale
        max_dimension = max(mesh.extents)
        scale_factor = 1.0 / max_dimension
        mesh.apply_scale(scale_factor)

        # Step 5: Export and Descriptors
        descriptors = ShapeDescriptors.from_mesh(mesh, model_class, model_name)  # assuming this is a predefined class
        base_model_name, _ = os.path.splitext(model_name)

        normalized_output_path = os.path.join(normalized_models_path, model_class)
        os.makedirs(normalized_output_path, exist_ok=True)

        # Construct the file path with the .obj extension explicitly added
        mesh_path = os.path.join(normalized_output_path, f"{base_model_name}.obj")
        mesh.export(mesh_path, file_type="obj")

        return descriptors

    return None


def load_model(path: tuple[str, str, str]) -> tuple[trimesh.Trimesh, str, str]:
    """
    Load model from path.
    :param path: Tuple containing the model's path, name and class.
    :return: Tuple containing the model's mesh, name and class.
    """
    mesh = trimesh.load_mesh(path[0])
    return mesh, path[1], path[2]


def main():
    """
    Main
    """
    # Store all paths to be processed
    paths_to_load = []

    for root, dirs, files in os.walk(models_path):
        len_files = len(files)
        if len(files) > 0:
            for i in range(len_files):
                file = files[i]
                model_class = os.path.basename(os.path.normpath(root))
                path = os.path.join(models_path, model_class, file)
                paths_to_load.append((path, model_class, file))

    # Use multiprocessing to parallelize the loading
    with Pool(processes=cpu_count()) as pool:
        meshes = pool.map(load_model, paths_to_load)

    average_model, _ = return_neighbors()
    average_mesh = next((m[0] for m in meshes if m[2] == average_model["Shape Name"]), None)

    target_faces = len(average_mesh.vertices)

    # Use multiprocessing to parallelize the processing
    with Pool(processes=cpu_count()) as pool:
        all_descriptors = list(
            tqdm(pool.imap_unordered(normalize_mesh, [(m, target_faces) for m in meshes]), total=len(meshes)))
    data_list = []

    # Remove all None elements
    all_descriptors = [descriptor for descriptor in all_descriptors if descriptor]

    for descriptor in tqdm(all_descriptors, desc="Saving Descriptors for all Shapes", leave=False):
        data = {
            "Model Class": descriptor.model_class,
            "Model Name": descriptor.model_name,
            "Surface Area": round(descriptor.surface_area, 3),
            "Compactness": round(descriptor.compactness, 3),
            "Rectangularity": round(descriptor.rectangularity, 3),
            "Diameter": round(descriptor.diameter, 3),
            "Convexity": round(descriptor.convexity, 3),
            "Eccentricity": round(descriptor.eccentricity, 3),
            "A3": [round(x, 3) for x in descriptor.A3],
            "D1": [round(x, 3) for x in descriptor.D1],
            "D2": [round(x, 3) for x in descriptor.D2],
            "D3": [round(x, 3) for x in descriptor.D3],
            "D4": [round(x, 3) for x in descriptor.D4],
        }
        data_list.append(data)

    df = pd.DataFrame(data_list)

    try:
        df.to_csv(database_path, index=False, sep=';')
    except OSError:
        try:
            path = os.path.join('tools', 'outputs', 'database2.csv')
            df.to_csv(path, index=False, sep=';')
        except OSError:
            path = os.path.join('outputs', 'database2.csv')
            df.to_csv(path, index=False, sep=';')


if __name__ == '__main__':
    main()
