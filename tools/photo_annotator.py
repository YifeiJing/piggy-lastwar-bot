import cv2 as cv
import numpy as np
import sys

def annotate_photo(image_path, pos):
    # Load the image
    img = cv.imread(image_path)
    if img is None:
        print(f"Error: Could not load image from {image_path}")
        return


    annotated_img = img.copy()
    # cv.drawContours(annotated_img, contours, -1, (0, 255, 0), 2)
    cv.rectangle(annotated_img, (pos[0], pos[1]), (pos[0] + 50, pos[1] + 50), (0, 255, 0), 2)
    # Display the annotated image
    cv.imwrite('dumps/annotated_image.png', annotated_img)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python photo_annotator.py <image_path> <x> <y>")
        sys.exit(1)

    image_path = sys.argv[1]
    x = int(sys.argv[2])
    y = int(sys.argv[3])

    annotate_photo(image_path, (x, y))