import face_recognition

def encode_face(image_path):

    image = face_recognition.load_image_file(image_path)

    encodings = face_recognition.face_encodings(image)

    if len(encodings) > 0:
        return encodings[0].tolist()

    return None


def compare_faces(known_encoding, unknown_image_path):

    unknown_image = face_recognition.load_image_file(unknown_image_path)

    unknown_encodings = face_recognition.face_encodings(unknown_image)

    if not unknown_encodings:
        return False

    result = face_recognition.compare_faces(
        [known_encoding],
        unknown_encodings[0]
    )

    return result[0]