from __future__ import annotations
import trimesh
import numpy as np
from numba import njit
from tools.descriptor_extraction import ShapeDescriptors
from pynndescent import NNDescent
from tqdm import tqdm

THRESHOLD = 500


def get_bb_lines(bounding_box: np.ndarray[float]) -> list[tuple[float, float]]:
    """
    Gets the bounding box connections of a shape's bounding box coordinates.
    :param bounding_box: Shape bounding box.
    :return: Bounding box connections
    """
    x0, y0, z0 = bounding_box[0][0], bounding_box[0][1], bounding_box[0][2]
    x1, y1, z1 = bounding_box[1][0], bounding_box[1][1], bounding_box[1][2]

    p000 = (x0, y0, z0)
    p001 = (x0, y0, z1)
    p010 = (x0, y1, z0)
    p011 = (x0, y1, z1)
    p100 = (x1, y0, z0)
    p101 = (x1, y0, z1)
    p110 = (x1, y1, z0)
    p111 = (x1, y1, z1)

    connections = [
        (p000, p001), (p000, p010), (p000, p100),
        (p111, p110), (p111, p101), (p111, p011),
        (p001, p101), (p001, p011),
        (p010, p110), (p010, p011),
        (p100, p101), (p100, p110),
    ]

    return connections


def get_basis_lines(bounding_box: np.ndarray, barycenter: np.ndarray) -> list[tuple[any, any]]:
    """
    Returns the 3D axis of a shape calculated at its center.
    :param bounding_box: Shape bounding box.
    :param barycenter: Shape barycenter (centroid).
    :return: Shape 3D axis
    """
    # Calculate the model's geometric center
    if bounding_box is not None:
        center_x = (bounding_box[0][0] + bounding_box[1][0]) / 2
        center_y = (bounding_box[0][1] + bounding_box[1][1]) / 2
        center_z = (bounding_box[0][2] + bounding_box[1][2]) / 2
    else:
        center_x, center_y, center_z = barycenter

    center = (center_x, center_y, center_z)

    # Define the offsets for the basis vectors
    offset = 0.25  # This can be adjusted based on desired length of basis vectors

    # Calculate endpoints of basis vectors centered at the model's origin
    i_pos = (center_x + offset, center_y, center_z)
    j_pos = (center_x, center_y + offset, center_z)
    k_pos = (center_x, center_y, center_z + offset)

    # Define the lines connecting the center to the endpoints of the basis vectors
    connections = [
        (center, i_pos),
        (center, j_pos),
        (center, k_pos),
    ]

    return connections


def resample(mesh: trimesh.Trimesh, target_vertices: int) -> trimesh.Trimesh:
    """
    Resamples a mesh to a specific target number of vertices.
    :param mesh: Model mesh.
    :param target_vertices: Target vertices to resample to.
    :return: Resampled mesh.
    """
    while len(mesh.vertices) > target_vertices + THRESHOLD or len(mesh.vertices) < target_vertices - THRESHOLD:
        # If number of vertices is too high, simplify
        if len(mesh.vertices) > target_vertices + THRESHOLD:
            new_face_count = target_vertices * (len(mesh.faces) / len(mesh.vertices))
            mesh = mesh.simplify_quadratic_decimation(new_face_count)

        # If number of vertices is too low, subdivide
        if len(mesh.vertices) < target_vertices - THRESHOLD:
            mesh = trimesh.Trimesh(*trimesh.remesh.subdivide(mesh.vertices, mesh.faces))
    return mesh


def normalize_single_features(mesh_features: ShapeDescriptors) -> None:
    """
    Normalizes the single features of all shapes.
    :param mesh_features: Shape descriptors of all meshes.
    """
    feature_values = [descriptor.get_single_features() for descriptor in mesh_features]

    features_array = np.array(feature_values)

    mean = np.mean(features_array, axis=0)
    std = np.std(features_array, axis=0)

    standardized_features = (features_array - mean) / std

    for i, descriptor in enumerate(mesh_features):
        descriptor.normalize_single_features(standardized_features[i])


@njit
def euclidean_distance(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Calculates the Euclidean distance between 2 samples.
    :param x1: 1st sample.
    :param x2: 2nd sample.
    :return: Euclidean distance between the 2 samples.
    """
    return np.sqrt(np.sum((x1 - x2) ** 2))


@njit
def cosine_distance(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Calculates the Cosine distance between 2 samples.
    :param x1: 1st sample.
    :param x2: 2nd sample.
    :return: Cosine distance between the 2 samples.
    """
    dot_product = np.dot(x1, x2)
    norm_x1 = np.linalg.norm(x1)
    norm_x2 = np.linalg.norm(x2)

    cosine_similarity = dot_product / (norm_x1 * norm_x2)

    # Cosine distance is complementary to cosine similarity
    cosine_distance = 1 - cosine_similarity

    return cosine_distance


@njit
def earth_movers_distance(x1, x2):
    """
    Calculates the Earth Mover's Distance between 2 samples
    (taken from: https://gist.github.com/jgraving/db2bf2fab8d623557e26eb363dd91af9/23e5df5b702f54e09984a04b83fa392edc6b8360)
    :param x1: 1st sample.
    :param x2: 2nd sample.
    :return: Earth Mover's Distance between the 2 samples.
    """
    n = len(x1)
    ac = 0
    bc = 0
    diff = 0
    for i in range(n):
        ac += x1[i]
        bc += x2[i]
        diff += abs(ac - bc)
    return diff


def get_best_matching_shapes(
        current_mesh, all_meshes, num_neighbors: int, distance_metric: str
) -> tuple[list[str], list[float]]:
    """
    Gets the n best-matching shapes of a query shape based on a distance metric.
    :param current_mesh: Mesh of the query shape.
    :param all_meshes: All database meshes except the query shape.
    :param num_neighbors: Number of best-matching shapes to return.
    :param distance_metric: Distance metric to use.
    :return: Tuple of the n best-matching shapes and their distances to the query shape.
    """
    distances = {}
    for model_name, mesh in all_meshes.items():
        if distance_metric == "Euclidean":
            current_features = np.array(current_mesh.get_weighted_normalized_features())
            mesh_features = np.array(mesh.get_weighted_normalized_features())

            distances[model_name] = euclidean_distance(current_features, mesh_features)
        elif distance_metric == "Cosine":
            current_features = np.array(current_mesh.get_weighted_normalized_features())
            mesh_features = np.array(mesh.get_weighted_normalized_features())

            distances[model_name] = cosine_distance(current_features, mesh_features)
        elif distance_metric == "EMD":
            current_features = np.array(current_mesh.get_weighted_normalized_features())
            mesh_features = np.array(mesh.get_weighted_normalized_features())

            distances[model_name] = earth_movers_distance(current_features, mesh_features)

        elif distance_metric == "Euclidean (Single) + EMD (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = euclidean_distance(current_single_features, mesh_single_features)
            histogram_distance = earth_movers_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.5 + histogram_distance * 0.5

        elif distance_metric == "Euclidean (Single) + Cosine (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = euclidean_distance(current_single_features, mesh_single_features)
            histogram_distance = cosine_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.04 + histogram_distance * 0.96
        elif distance_metric == "Cosine (Single) + EMD (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = cosine_distance(current_single_features, mesh_single_features)
            histogram_distance = earth_movers_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.5 + histogram_distance * 0.5
        elif distance_metric == "Cosine (Single) + Euclidean (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = cosine_distance(current_single_features, mesh_single_features)
            histogram_distance = euclidean_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.4 + histogram_distance * 0.6
        elif distance_metric == "EMD (Single) + Euclidean (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = earth_movers_distance(current_single_features, mesh_single_features)
            histogram_distance = euclidean_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.03 + histogram_distance * 0.97
        elif distance_metric == "EMD (Single) + Cosine (Histogram)":
            current_single_features = np.array(current_mesh.get_normalized_single_features())
            current_histogram_features = np.array(current_mesh.get_normalized_histogram_features())

            mesh_single_features = np.array(mesh.get_normalized_single_features())
            mesh_histogram_features = np.array(mesh.get_normalized_histogram_features())

            single_distance = earth_movers_distance(current_single_features, mesh_single_features)
            histogram_distance = cosine_distance(current_histogram_features, mesh_histogram_features)

            distances[model_name] = single_distance * 0.01 + histogram_distance * 0.99

    sorted_distances = sorted(distances.items(), key=lambda item: item[1])
    best_matching_shapes = [model_name for model_name, _ in sorted_distances[:num_neighbors]]
    distances = [distance[1] for distance in distances.items()]

    return best_matching_shapes, distances


def calculate_shapes_per_class(shapes: list[any]) -> dict[str, int]:
    """
    Calculates the number of shapes of each shape class.
    :param shapes: List of all meshes, their names and class names.
    :return: Dictionary where the keys are the shape classes and the values are the number of shapes of that class.
    """
    shapes_per_class = {}
    for shape in shapes:
        shape_class = shape[5]
        if shape_class in shapes_per_class:
            shapes_per_class[shape_class] += 1
        else:
            shapes_per_class[shape_class] = 1
    return shapes_per_class


def calculate_precision(name: str, matched_shapes: list[any], all_classes: dict[str, list[str]]) -> tuple[float, str]:
    """
    Calculates the precision of a query.
    :param name: Name of the query shape.
    :param matched_shapes: N best-matching shapes.
    :param all_classes: All classes.
    :return: Precision of the query.
    """
    tp = 0
    fp = 0
    correct_class = None
    for key, values in all_classes.items():
        if name in values:
            correct_class = key
            break

    if correct_class:
        for matched_shape in matched_shapes:
            if matched_shape in all_classes.get(correct_class, []):
                tp += 1
            else:
                fp += 1
        return tp / (tp + fp) if (tp + fp) > 0 else 0, correct_class
    return 0.0, ""


def calculate_recall(name: str, matched_shapes: list[any], all_classes: dict[str, list[str]]) -> tuple[float, str]:
    """
    Calculates the recall of a query.
    :param name: Name of the query shape.
    :param matched_shapes: N best-matching shapes.
    :param all_classes: All classes.
    :return: Recall of the query.
    """
    tp = 0
    correct_class = None
    for key, values in all_classes.items():
        if name in values:
            correct_class = key
            break
    if correct_class:
        for matched_shape in matched_shapes:
            if matched_shape in all_classes.get(correct_class, []):
                tp += 1
        fn = len(all_classes.get(correct_class, [])) - tp
        return tp / (tp + fn) if (tp + fn) > 0 else 0, correct_class
    return 0.0, ""


def evaluate_query(
        query_type: str, all_shapes: dict[any], k: int, shapes_per_class: dict[str, int],
        all_classes: dict[str, list[str]], index: NNDescent, distance_metric: str
) -> tuple[dict[str, float | int], dict[str, float | int], dict[str, float | int]]:
    """
    Evaluates quality of selected query.
    :param query_type: Type of query (Custom or ANN).
    :param all_shapes: All shapes.
    :param k: Number of best-matching shapes to return.
    :param shapes_per_class: Number of shapes of each class.
    :param all_classes: All classes.
    :param index: Query index used for the ANN query.
    :param distance_metric: Distance metric to use.
    :return: Precisions, recalls and f1-scores for all classes, as well as for each class separately.
    """
    precisions = {}
    recalls = {}
    f1_scores = {}
    average_precision = 0
    average_recall = 0
    # Query all shapes
    for name, descriptor in tqdm(all_shapes.items(),
                                 desc=f"Finding the {k} Best Matching Shapes for each Shape", leave=False):
        # Query based on selected query type
        if query_type == "Custom":
            matching_names, _ = get_best_matching_shapes(
                descriptor, {key: value for key, value in all_shapes.items() if key != name}, k, distance_metric
            )
        elif query_type == "ANN":
            neighbor_indexes, _ = index.query(np.array([descriptor.get_weighted_normalized_features()]), k=k + 1)
            matching_names = [list(all_shapes.keys())[k] for k in neighbor_indexes.flatten().tolist()[1:]]
        else:
            print(f"No implementation for the query type: {query_type}")
            print("Exiting application...")
            exit()

        precision, correct_class = calculate_precision(name, matching_names, all_classes)
        recall, _ = calculate_recall(name, matching_names, all_classes)
        average_precision += precision
        average_recall += recall

        if correct_class in precisions:
            precisions[correct_class] += precision
            recalls[correct_class] += recall
        else:
            precisions[correct_class] = precision
            recalls[correct_class] = recall

    # Calculate averages
    for shape_class in shapes_per_class.keys():
        precisions[shape_class] /= shapes_per_class[shape_class]
        recalls[shape_class] /= shapes_per_class[shape_class]

    average_precision /= len(all_shapes)
    average_recall /= len(all_shapes)

    precision_sum_recall = average_recall + average_precision
    if precision_sum_recall > 0:
        f1_score = 2 * average_precision * average_precision / precision_sum_recall
    else:
        f1_score = 0

    precisions["Average"] = average_precision
    recalls["Average"] = average_recall
    f1_scores["Average"] = f1_score

    for shape_class in precisions.keys():
        precision_sum_recall = precisions[shape_class] + recalls[shape_class]
        if precision_sum_recall > 0:
            f1_scores[shape_class] = 2 * precisions[shape_class] * recalls[shape_class] / precision_sum_recall
        else:
            f1_scores[shape_class] = 0

    return precisions, recalls, f1_scores
