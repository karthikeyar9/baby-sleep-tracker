import json
import logging
import os
import pickle

import cv2
import numpy as np
from PIL import Image
from sklearn import svm

from backend.config import (
    BLANKET_MODEL_PATH,
    BLANKET_MODEL_INPUT_DIR,
    BLANKET_MODEL_OUTPUT_DIR,
    IMAGE_DATA_JSON,
    CLASSIFIER_RESOLUTION,
)
from backend.utils.image import maintain_aspect_ratio_resize

logger = logging.getLogger(__name__)


def load_model():
    """Load the blanket SVM model from disk. Returns None if not found."""
    try:
        with open(BLANKET_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning("No blanket model found at startup: %s", e)
        logger.info("No blanket model found at startup: %s", e)
        return None


def save_model(model):
    """Persist the trained SVM model to disk."""
    with open(BLANKET_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


def predict(model, image):
    """Run prediction on a preprocessed image. Returns probability array."""
    blurred = cv2.GaussianBlur(image, (3, 3), 0)
    return model.predict_proba([blurred.flatten()])


def train_model(all_images_flat, all_labels):
    """Train a new SVM classifier and save it."""
    clf = svm.SVC(probability=True, C=0.1, gamma=0.0001, kernel="poly")
    clf.fit(all_images_flat, all_labels)
    save_model(clf)
    # Reload to ensure consistency
    return load_model()


def retrain_from_images(focus_bounding_box):
    """Retrain the model using all images in the input directory with the given crop bounds.

    Returns the newly trained model.
    """
    master_image_data = {"baby": [], "no_baby": []}

    input_paths = os.listdir(BLANKET_MODEL_INPUT_DIR)
    for label_dir in input_paths:
        label_path = os.path.join(BLANKET_MODEL_INPUT_DIR, label_dir)
        if not os.path.isdir(label_path):
            continue
        for filename in os.listdir(label_path):
            image_path = os.path.join(label_path, filename)
            image = Image.open(image_path)
            image_data = np.asarray(image)

            x, y, w, h = focus_bounding_box
            if y is None:
                continue
            cropped = image_data[y:y + h, x:x + w]
            resized, _ = maintain_aspect_ratio_resize(cropped, width=CLASSIFIER_RESOLUTION)
            blurred = cv2.GaussianBlur(resized, (3, 3), 0)

            master_image_data[label_dir].append(blurred.flatten().tolist())

    # Save training data
    os.makedirs(BLANKET_MODEL_OUTPUT_DIR, exist_ok=True)
    with open(IMAGE_DATA_JSON, "w") as f:
        json.dump(master_image_data, f)

    all_images_flat = master_image_data["baby"] + master_image_data["no_baby"]
    all_labels = (["baby"] * len(master_image_data["baby"])) + (
        ["no_baby"] * len(master_image_data["no_baby"])
    )

    return train_model(all_images_flat, all_labels)


def retrain_with_new_sample(classification, image_path, focus_bounding_box):
    """Add a single new sample and retrain.

    Returns the newly trained model.
    """
    image = Image.open(image_path)
    image_data = np.asarray(image)

    x, y, w, h = focus_bounding_box
    cropped = image_data[y:y + h, x:x + w]
    resized, _ = maintain_aspect_ratio_resize(cropped, width=CLASSIFIER_RESOLUTION)
    blurred = cv2.GaussianBlur(resized, (3, 3), 0)

    # Load existing training data
    all_images_dict = {}
    if os.path.exists(IMAGE_DATA_JSON):
        with open(IMAGE_DATA_JSON, "r") as f:
            all_images_dict = json.load(f)

    if "baby" not in all_images_dict:
        all_images_dict["baby"] = []
    if "no_baby" not in all_images_dict:
        all_images_dict["no_baby"] = []

    all_images_dict[classification].append(blurred.flatten().tolist())

    with open(IMAGE_DATA_JSON, "w") as f:
        json.dump(all_images_dict, f)

    all_images_flat = all_images_dict["baby"] + all_images_dict["no_baby"]
    all_labels = (["baby"] * len(all_images_dict["baby"])) + (
        ["no_baby"] * len(all_images_dict["no_baby"])
    )

    return train_model(all_images_flat, all_labels)
