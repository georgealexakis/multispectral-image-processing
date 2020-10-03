from __future__ import print_function
import cv2
import sys
import numpy as np
import copy
import time


class BandSeparator:
    # Number of matches
    MAX_FEATURES = 1000
    # Lower is more accurate (higher takes more features)
    GOOD_MATCH_PERCENT = 0.15
    # Capture best homography matrix
    BEST_HOMOGRAPHY = []
    MAX_MATCHES = 0
    MIN_DIFF = 255
    HF_PATH = "data/resources/homography.yaml"
    HOMOGRAPHY_MATRIX = []

    # Image encoding for grayscale and colored images
    IME_B = "mono8"
    IME_C = "bgr8"

    # Camera topics and camera info
    pub_b = []
    CAMERA_INFO = []
    RAW_WIDTH = 1280
    RAW_HEIGHT = 1024
    CRAW_WIDTH = 1278
    CRAW_HEIGHT = 1017
    BAND_WIDTH = 426
    BAND_HEIGHT = 339
    D_MODEL = "plumb_bob"
    FRAME_ID = "multispectral_band_frame"

    # Crosstalk correction coefficients from manifacturer resources
    wCoefCrossTalk = [[0 for i in range(9)] for j in range(9)]
    whiteReferenceCoefficients = []

    # Reading order of every super pixel starts from (2, 0)
    bandsOrder = [4, 8, 0, 3, 2, 1, 5, 6, 7]

    # Reading order of every super pixel starts from (0, 0)
    bandsOrderCo = [6, 7, 8, 0, 1, 2, 3, 4, 5]

    # Set offset to begin from (2, 0)
    offsetX = 2
    offsetY = 0

    # Flat-field and dark-field correction images
    F = np.ones((1024, 1280), np.uint8)
    D = np.ones((1024, 1280), np.uint8)
    FF_PATH = "data/flat-field-correction/flat-field.png"
    DF_PATH = "data/flat-field-correction/dark-field.png"

    # Keyboard buttons triggers
    buttonTriggers = [False, False, False, False, False, False, False, False]

    # White balance selected area positions (from positions[0] to positions[3]) and status (positions[4])
    positions = [-1, -1, -1, -1, -1]

    # FPS counter
    startTime = time.time()
    displayRate = 1
    counter = 0

    # Paths
    FPS_PATH = "data/resources/fps_log.yaml"
    WR_PATH = "data/resources/wr_coefficients.yaml"
    MP_PATH = "data/resources/parameters.yaml"
    DS_PATH = "data/dataset/"
    SI_PATH = "data/simulation/"
    MI_NAME = "_multispectral_camera.png"
    KR_NAME = "_kinect_hd_rgb.png"
    KD_NAME = "_kinect_hd_depth.png"

    # Termination criteria for point detection and chessboard pattern size
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
    patternsize = (7, 5)

    def __init__(self):
        # Optimization in OpenCV
        cv2.useOptimized()

        # Load CMS-V camera manufacturer parameters
        self.loadManufacturerParameters()
        # Load white reference coefficients
        self.loadWhiteReference()

        # Display camera information and initial parameters
        print("\n******** Band separator started ***********\n")
        print("Camera: " + self.cameraReference + "\nM.S.N.: " + self.cameraManufacturerSN +
              "\nC.S.N.: " + self.cameraSN + "\nCrosstalk Coefficients")
        self.printCrosstalkCoefficients()
        print("Crosstalk Correction is off.\nFlat-field Correction is off.\nBlack-field Correction is off.\nWhite Reference is off.\nUse keyboard buttons c - Crosstalk, e - Flat-field, f - Flat-field capture, d - Dark-field capture, w - White reference, n - Display Indexes, b - Display bands, r - Reset values.")

        # Initialize the images for flat-field correction (flat-field image and dark-field image)
        self.F = cv2.imread(self.FF_PATH, 0)
        self.D = cv2.imread(self.DF_PATH, 0)

        # Initialize raw image window and set mouse listener
        cv2.namedWindow("Raw Image", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Raw Image", self.onMouse, self.positions)

        # Start processing
        # Edit the paths below to use dataset or a single image
        # choice = 0 for single image demo, choice = 1 for stream of frames demo
        # registrationApproach = 0 for feature-based image registration, registrationApproach = 1 for corener-based image registration
        choice = 0
        registrationApproach = 0
        if choice == 0:
            # Single image frame in simulation folder (play in loop)
            while(True):
                # Choose prefix and folder id
                prefix = 2020511
                folder = 1
                rawImage = cv2.imread(
                    self.SI_PATH + str(folder) + "/" + str(prefix) + self.MI_NAME, 0)
                krgbImage = cv2.imread(
                    self.SI_PATH + str(folder) + "/" + str(prefix) + self.KR_NAME)
                kdepthImage = cv2.imread(
                    self.SI_PATH + str(folder) + "/" + str(prefix) + self.KD_NAME, 0)
                self.performProcessing(
                    rawImage, krgbImage, kdepthImage, choice, registrationApproach)
        else:
            # Stream of frames in dataset folder (play in loop)
            # Stream length from 0 - 10
            self.ci = 0
            while(self.ci < 11):
                print("-----")
                print(self.DS_PATH + str(self.ci) + self.MI_NAME)
                print(self.DS_PATH + str(self.ci) + self.KR_NAME)
                print(self.DS_PATH + str(self.ci) + self.KD_NAME)
                print("-----")
                rawImage = cv2.imread(
                    self.DS_PATH + str(self.ci) + self.MI_NAME, 0)
                krgbImage = cv2.imread(
                    self.DS_PATH + str(self.ci) + self.KR_NAME)
                kdepthImage = cv2.imread(
                    self.DS_PATH + str(self.ci) + self.KD_NAME, 0)
                self.performProcessing(
                    rawImage, krgbImage, kdepthImage, choice, registrationApproach)
                self.ci = self.ci + 1
                if self.ci == 11:
                    print("Play loop again.")
                    self.ci = 0

    # Receive images from multispectral camera for further processing
    def performProcessing(self, rawImage, krgbImage, kdepthImage, action, approach):
        # Seperate every row of the band matrix.
        # Band seperation follows the matrix below:
        # 	+----------+----------+----------+
        # 	|  Band 5  |  Band 9  |  Band 1  |
        # 	|----------+----------+----------|
        # 	|  Band 4  |  Band 3  |  Band 2  |
        # 	|----------+----------+----------|
        # 	|  Band 6  |  Band 7  |  Band 8  |
        #	+----------+----------+----------+

        # Check raw image size if it matches the right dimensions 1024x1280
        if rawImage.shape[0] == self.RAW_HEIGHT and rawImage.shape[1] == self.RAW_WIDTH:

            # Flat-field correction
            if(self.buttonTriggers[1]):
                rawImage = self.flatFieldCorrection(rawImage)

            # Reading order is line by line for bands [5 9 1; 4 3 2; 6 7 8]
            images = np.array([rawImage[0+self.offsetX::3, 0+self.offsetY::3],
                               rawImage[0+self.offsetX::3, 1+self.offsetY::3],
                               rawImage[0+self.offsetX::3, 2+self.offsetY::3],
                               rawImage[1+self.offsetX::3, 0+self.offsetY::3],
                               rawImage[1+self.offsetX::3, 1+self.offsetY::3],
                               rawImage[1+self.offsetX::3, 2+self.offsetY::3],
                               rawImage[2+self.offsetX::3, 0+self.offsetY::3],
                               rawImage[2+self.offsetX::3, 1+self.offsetY::3],
                               rawImage[2+self.offsetX::3, 2+self.offsetY::3]])

            # Crop images to fit exactly to the dimensions of 426x339 every band.
            # It removes the last (2 - offsetY) = 2 pixels of the columns and the last (7 - offsetX) = 5
            # pixels from the rows resuling in image size equals to 1278x1017,
            # due to the precise band seperation to 426x339 for every band.
            for i in range(9):
                images[i] = images[i][0:self.BAND_HEIGHT, 0:self.BAND_WIDTH]

            # White reference array
            wrImages = []
            # Normalized of white reference array
            wrnImages = []
            # White reference process
            for i in range(9):
                wrImages.append(np.multiply(
                    images[i], self.whiteReferenceCoefficients[self.bandsOrderCo[i]]))
            # Deep copy of original values to the normalized array
            wrnImages = copy.deepcopy(wrImages)
            # Normalize white reference array for the display (remove values higher than 255 and values lower than 0 and change type to uint8)
            for i in range(9):
                wrnImages[i][wrnImages[i] > 255] = 255
                wrnImages[i][wrnImages[i] < 0] = 0
                wrnImages[i] = wrnImages[i].astype(np.uint8)

            # Crosstalk correction with super-pixels to increase the contrast
            ctImages = self.computeCrosstalkCorrection(wrImages)

            # Display raw image
            self.dispalyRawImage(rawImage)

            # Set white reference values
            self.setWhiteReference(rawImage, self.buttonTriggers[4])

            # Choose the images to publish and copy them to the final array
            if (self.buttonTriggers[0]):
                images = copy.deepcopy(ctImages)
            else:
                images = copy.deepcopy(wrnImages)

            # Build the grid of bands
            bandsGrid = self.mergeBands(images)

            # NDVI calculation using band 3 and band 6
            ndvi, ndviColor = self.ndviCalculator(images[4], images[6])
            erdImageNDVI, segImageNDVI = self.segmentation(ndvi)

            # Vegetation indexes
            if (self.buttonTriggers[5]):
                # GNDVI calculation using band 1 and band 6
                gndvi, gndviColor = self.ndviCalculator(images[2], images[6])
                erdImageGNDVI, segImageGNDVI = self.segmentation(gndvi)

                # SAVI calculation using band 3 and band 6
                savi, saviColor = self.saviCalculator(images[4], images[6])
                erdImageSAVI, segImageSAVI = self.segmentation(savi)

                # GSAVI calculation using band 1 and band 6
                gsavi, gsaviColor = self.gsaviCalculator(images[2], images[6])
                erdImageGSAVI, segImageGSAVI = self.segmentation(gsavi)

                # MCARI calculation using band 1, band 4 and band 5
                mcari = self.mcariCalculator(images[2], images[3], images[0])

                # MSR calculation using band 3 and band 6
                msr, msrColor = self.msrCalculator(images[4], images[6])
                erdImageMSR, segImageMSR = self.segmentation(msr)

                # TVI, MTVI1, MTVI2 calculation using band 1, band 3, band 6, band 4 and band 7
                tvi, mtvi1, mtvi2 = self.tviCalculator(
                    images[2], images[4], images[6], images[3], images[7])

                # Display the images of the vegetation indexes
                self.displayImage(ndvi, "NDVI")
                self.displayImage(ndviColor, "NDVI Colormap")
                self.displayImage(savi, "SAVI")
                self.displayImage(saviColor, "SAVI Colormap")
                self.displayImage(gsavi, "GSAVI")
                self.displayImage(gsaviColor, "GSAVI Colormap")
                self.displayImage(gndvi, "GNDVI")
                self.displayImage(gndviColor, "GNDVI Colormap")
                self.displayImage(mcari, "MCARI")
                self.displayImage(msr, "MSR")
                self.displayImage(msrColor, "MSR Colormap")
                self.displayImage(tvi, "TVI")
                self.displayImage(mtvi1, "MTVI1")
                self.displayImage(mtvi2, "MTVI2")
                self.displayImage(segImageNDVI, "Segmented Image NDVI")
                self.displayImage(erdImageNDVI, "Eroded & Dilated Image NDVI")
                self.displayImage(segImageGNDVI, "Segmented Image GNDVI")
                self.displayImage(
                    erdImageGNDVI, "Eroded & Dilated Image GNDVI")
                self.displayImage(segImageSAVI, "Segmented Image SAVI")
                self.displayImage(erdImageSAVI, "Eroded & Dilated Image SAVI")
                self.displayImage(segImageGSAVI, "Segmented Image GSAVI")
                self.displayImage(
                    erdImageGSAVI, "Eroded & Dilated Image GSAVI")
                self.displayImage(segImageMSR, "Segmented Image MSR")
                self.displayImage(erdImageMSR, "Eroded & Dilated Image MSR")
            else:
                cv2.destroyWindow("NDVI")
                cv2.destroyWindow("NDVI Colormap")
                cv2.destroyWindow("GNDVI")
                cv2.destroyWindow("GNDVI Colormap")
                cv2.destroyWindow("SAVI")
                cv2.destroyWindow("SAVI Colormap")
                cv2.destroyWindow("GSAVI")
                cv2.destroyWindow("GSAVI Colormap")
                cv2.destroyWindow("MCARI")
                cv2.destroyWindow("MSR")
                cv2.destroyWindow("MSR Colormap")
                cv2.destroyWindow("TVI")
                cv2.destroyWindow("MTVI1")
                cv2.destroyWindow("MTVI2")
                cv2.destroyWindow("Segmented Image NDVI")
                cv2.destroyWindow("Eroded & Dilated Image NDVI")
                cv2.destroyWindow("Segmented Image GNDVI")
                cv2.destroyWindow("Eroded & Dilated Image GNDVI")
                cv2.destroyWindow("Segmented Image SAVI")
                cv2.destroyWindow("Eroded & Dilated Image SAVI")
                cv2.destroyWindow("Segmented Image GSAVI")
                cv2.destroyWindow("Eroded & Dilated Image GSAVI")
                cv2.destroyWindow("Segmented Image MSR")
                cv2.destroyWindow("Eroded & Dilated Image MSR")

            # Display or not final bands after pre-processing
            if (self.buttonTriggers[6]):
                self.displayImage(
                    bandsGrid, "Band 8(828nm), Band 1(560nm), Band 2(595nm); Band 7(791nm), Band 9(Panchromatic filter), Band 3(634nm); Band 6(752nm), Band 5(713nm), Band 4(673nm)")
            else:
                cv2.destroyWindow(
                    "Band 8(828nm), Band 1(560nm), Band 2(595nm); Band 7(791nm), Band 9(Panchromatic filter), Band 3(634nm); Band 6(752nm), Band 5(713nm), Band 4(673nm)")

            # Bilinear Interpolation for resizing band 3 to 1278x1017
            b3I = cv2.resize(images[4], (1278, 1017),
                             interpolation=cv2.INTER_LINEAR)

            # Image registration by using multispectal band 3 and Kinect images
            if(approach == 0):
                self.featureRegistrator(b3I, krgbImage, kdepthImage)
            else:
                self.cornerRegistrator(b3I, krgbImage, kdepthImage)

            self.setOperation(cv2.waitKey(action), rawImage)

            # Log FPS to fps_log.yaml
            self.counter += 1
            if(time.time() - self.startTime) > self.displayRate:
                fps = self.counter / (time.time() - self.startTime)
                fs = cv2.FileStorage(self.FPS_PATH, cv2.FILE_STORAGE_WRITE)
                fs.write("FPS", fps)
                fs.release
                self.counter = 0
                self.startTime = time.time()
        else:
            print("Wrong input image dimensions.")

    # Display image
    def displayImage(self, img, title):
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, 500, 500)
        cv2.imshow(title, img)

    # Mouse listener for white balance area selection
    def onMouse(self, event, x, y, flags, pixelPositions):
        positions = pixelPositions
        if event == cv2.EVENT_LBUTTONDOWN:
            if (x >= 0) and (y >= 0) and (x <= 1280) and (y <= 1024):
                if x >= 1278:
                    positions[0] = 1278
                else:
                    positions[0] = x
                if y >= 1022:
                    positions[1] = 1022
                else:
                    positions[1] = y
                positions[2] = -1
                positions[3] = -1
                positions[4] = 0
                print("White Reference Point 1 -> P0: " + str(positions[0]) + " / P1: " + str(
                    positions[1]) + " - (Input) x: " + str(x) + " / y: " + str(y))
            else:
                positions[0] = -1
                positions[1] = -1
                positions[2] = -1
                positions[3] = -1
        elif event == cv2.EVENT_MOUSEMOVE:
            if positions[4] == 0:
                positions[2] = x
                positions[3] = y
        elif event == cv2.EVENT_LBUTTONUP:
            if (x >= 0) and (y >= 0) and (x <= 1280) and (y <= 1024):
                if ((positions[0] == x) and (positions[1] == y)) or ((positions[0] == x + 1) and (positions[1] == y + 1)) or ((positions[0] == x + 2) and (positions[1] == y + 2)):
                    positions[2] = positions[0] + 2
                    positions[3] = positions[1] + 2
                elif (positions[0] == x) or (positions[0] == x + 1) or (positions[0] == x + 2):
                    positions[2] = positions[0] + 2
                    positions[3] = y
                elif (positions[1] == y) or (positions[1] == y + 1) or (positions[1] == y + 2):
                    positions[2] = x
                    positions[3] = positions[1] + 2
                else:
                    positions[2] = x
                    positions[3] = y
                positions[4] = 1
                print("White Reference Point 2 -> P2: " + str(positions[2]) + " / P3: " + str(
                    positions[3]) + " - (Input) x: " + str(x) + " / y: " + str(y))
            else:
                positions[0] = -1
                positions[1] = -1
                positions[2] = -1
                positions[3] = -1

    # Calculate cross-talk correction for every single pixel
    def computeCrosstalkCorrection(self, images):
        # Cross-talk correction variable declaration and initialization
        ctImages = []
        # Crosstalk correction multiply and sum process as it is in the formula
        for i in range(9):
            temp = []
            for j in range(9):
                temp.append(np.multiply(
                    images[j], self.wCoefCrossTalk[self.bandsOrder[j]][self.bandsOrder[i]]))
            ctImages.append(sum(temp))
        # Remove values higher than 255 and values lower than 0 and change type to uint8
        for i in range(9):
            ctImages[i][ctImages[i] > 255] = 255
            ctImages[i][ctImages[i] < 0] = 0
            ctImages[i] = ctImages[i].astype(np.uint8)
        return ctImages

    # Calculate NDVI values with custom colormap
    def ndviCalculator(self, b3, b6):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # NDVI = (NIR - RED) / (NIR + RED)
        # Change type to float32
        b3f = b3.astype(np.float32)
        b6f = b6.astype(np.float32)
        # Perform the calculations of the formula (NDVI values from -1.0 to 1.0)
        ndvi = np.divide(np.subtract(b6f, b3f), np.add(b6f, b3f))
        # Normalized NDVI values from 0.0 to 1.0
        ndviNorm1 = np.add(np.multiply(ndvi, 0.5), 0.5)
        # Normalized NDVI values from 0.0 to 255.0
        ndviNorm2 = np.multiply(ndviNorm1, 255)
        # Normalized NDVI values to export integer values
        ndviNorm3 = ndviNorm2.astype(np.uint8)
        # Colors for colormapping RGB
        ndviColor = np.zeros((339, 426, 3), np.uint8)

        # Colors for color-mapping in RGB palette
        # NDVI value and the coresponding RGB color for vegetation (from 0.0 to 1.0)
        #   0.00-0.05: RGB(234, 233, 189)
        #   0.05-0.10: RGB(215, 211, 148)
        #   0.10-0.15: RGB(202, 189, 119)
        #   0.15-0.20: RGB(175, 175, 77)
        #   0.20-0.30: RGB(128, 169, 5)
        #   0.30-0.40: RGB(12, 127, 0)
        #   0.40-0.50: RGB(0, 94, 0)
        #   0.50-0.60: RGB(0, 59, 1)
        #   0.60-1.00: RGB(0, 9, 0)

        # NDVI value and the coresponding RGB color for other materials such as snow and ice, water, buildings (from 0.0 to -1.0)
        #    (0.00)-(-0.05): RGB(128, 128, 128)
        #   (-0.05)-(-0.25): RGB(96, 96, 96)
        #   (-0.25)-(-0.50): RGB(64, 64, 64)
        #   (-0.50)-(-1.00): RGB(32, 32, 32)

        # NDVI coloring for different materials
        # Soil, vegetation and other materials respectievly
        # The colors are BGR not RGB
        ndviColor[ndvi >= 0.00] = [189, 233, 234]
        ndviColor[ndvi > 0.05] = [148, 211, 215]
        ndviColor[ndvi > 0.10] = [119, 189, 202]
        ndviColor[ndvi > 0.15] = [77, 175, 175]
        ndviColor[ndvi > 0.20] = [5, 169, 128]
        ndviColor[ndvi > 0.30] = [0, 127, 12]
        ndviColor[ndvi > 0.40] = [0, 94, 0]
        ndviColor[ndvi > 0.50] = [1, 59, 0]
        ndviColor[ndvi > 0.60] = [0, 9, 0]
        ndviColor[ndvi < 0.00] = [128, 128, 128]
        ndviColor[ndvi < -0.05] = [96, 96, 96]
        ndviColor[ndvi < -0.25] = [64, 64, 64]
        ndviColor[ndvi < -0.50] = [32, 32, 32]
        return ndviNorm3, ndviColor

    # Calculate GNDVI values with custom colormap
    def gndviCalculator(self, b1, b6):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # GNDVI = (NIR - GREEN) / (NIR + GREEN)
        # GREEN (green band 1 (560nm) is not accurate needs to be approximately 510 nm for real green band)
        # Change type to float32
        b1f = b1.astype(np.float32)
        b6f = b6.astype(np.float32)
        # Perform the calculations of the formula (GNDVI values from -1.0 to 1.0)
        gndvi = np.divide(np.subtract(b6f, b1f), np.add(b6f, b1f))
        # Normalized GNDVI values from 0.0 to 1.0
        gndviNorm1 = np.add(np.multiply(gndvi, 0.5), 0.5)
        # Normalized GNDVI values from 0.0 to 255.0
        gndviNorm2 = np.multiply(gndviNorm1, 255)
        # Normalized GNDVI values to export integer values
        gndviNorm3 = gndviNorm2.astype(np.uint8)
        # Colors for colormapping RGB
        gndviColor = np.zeros((339, 426, 3), np.uint8)

        # Colors for color-mapping in RGB palette
        # GNDVI coloring for different materials
        # Soil, vegetation and other materials respectievly
        # The colors are BGR not RGB
        gndviColor[gndvi >= 0.00] = [189, 233, 234]
        gndviColor[gndvi > 0.05] = [148, 211, 215]
        gndviColor[gndvi > 0.10] = [119, 189, 202]
        gndviColor[gndvi > 0.15] = [77, 175, 175]
        gndviColor[gndvi > 0.20] = [5, 169, 128]
        gndviColor[gndvi > 0.30] = [0, 127, 12]
        gndviColor[gndvi > 0.40] = [0, 94, 0]
        gndviColor[gndvi > 0.50] = [1, 59, 0]
        gndviColor[gndvi > 0.60] = [0, 9, 0]
        gndviColor[gndvi < 0.00] = [128, 128, 128]
        gndviColor[gndvi < -0.05] = [96, 96, 96]
        gndviColor[gndvi < -0.25] = [64, 64, 64]
        gndviColor[gndvi < -0.50] = [32, 32, 32]
        return gndviNorm3, gndviColor

    # Calculate SAVI values with custom colormap
    def saviCalculator(self, b3, b6):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # SAVI = ((1 + L)(NIR - RED)) / (NIR + RED + L)
        # Change type to float32
        L = 0.5
        b3f = b3.astype(np.float32)
        b6f = b6.astype(np.float32)
        # Perform the calculations of the formula (SAVI values from -1.0 to 1.0)
        savi = np.divide(np.multiply(
            (1 + L), np.subtract(b6f, b3f)), np.add(np.add(b6f, b3f), L))
        # Normalized SAVI values from 0.0 to 1.0
        saviNorm1 = np.add(np.multiply(savi, 0.5), 0.5)
        # Normalized SAVI values from 0.0 to 255.0
        saviNorm2 = np.multiply(saviNorm1, 255)
        # Normalized SAVI values to export integer values
        saviNorm3 = saviNorm2.astype(np.uint8)
        # Colors for colormapping RGB
        saviColor = np.zeros((339, 426, 3), np.uint8)

        # Colors for color-mapping in RGB palette
        # SAVI coloring for different materials
        # Soil, vegetation and other materials respectievly
        # The colors are BGR not RGB
        saviColor[savi >= 0.00] = [189, 233, 234]
        saviColor[savi > 0.05] = [148, 211, 215]
        saviColor[savi > 0.10] = [119, 189, 202]
        saviColor[savi > 0.15] = [77, 175, 175]
        saviColor[savi > 0.20] = [5, 169, 128]
        saviColor[savi > 0.30] = [0, 127, 12]
        saviColor[savi > 0.40] = [0, 94, 0]
        saviColor[savi > 0.50] = [1, 59, 0]
        saviColor[savi > 0.60] = [0, 9, 0]
        saviColor[savi < 0.00] = [128, 128, 128]
        saviColor[savi < -0.05] = [96, 96, 96]
        saviColor[savi < -0.25] = [64, 64, 64]
        saviColor[savi < -0.50] = [32, 32, 32]
        return saviNorm3, saviColor

    # Calculate GSAVI values with custom colormap (green band 1 (560nm) is not accurate need to be approximately 510 nm)
    def gsaviCalculator(self, b1, b6):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # GSAVI = ((1 + L)(NIR - GREEN)) / (NIR + GREEN + L)
        # GREEN (green band 1 (560nm) is not accurate needs to be approximately 510 nm for real green band)
        # Change type to float32
        L = 0.5
        b1f = b1.astype(np.float32)
        b6f = b6.astype(np.float32)
        # Perform the calculations of the formula (GSAVI values from -1.0 to 1.0)
        gsavi = np.divide(np.multiply(
            (1 + L), np.subtract(b6f, b1f)), np.add(np.add(b6f, b1f), L))
        # Normalized GSAVI values from 0.0 to 1.0
        gsaviNorm1 = np.add(np.multiply(gsavi, 0.5), 0.5)
        # Normalized GSAVI values from 0.0 to 255.0
        gsaviNorm2 = np.multiply(gsaviNorm1, 255)
        # Normalized GSAVI values to export integer values
        gsaviNorm3 = gsaviNorm2.astype(np.uint8)
        # Colors for colormapping RGB
        gsaviColor = np.zeros((339, 426, 3), np.uint8)

        # Colors for color-mapping in RGB palette
        # GSAVI coloring for different materials
        # Soil, vegetation and other materials respectievly
        # The colors are BGR not RGB
        gsaviColor[gsavi >= 0.00] = [189, 233, 234]
        gsaviColor[gsavi > 0.05] = [148, 211, 215]
        gsaviColor[gsavi > 0.10] = [119, 189, 202]
        gsaviColor[gsavi > 0.15] = [77, 175, 175]
        gsaviColor[gsavi > 0.20] = [5, 169, 128]
        gsaviColor[gsavi > 0.30] = [0, 127, 12]
        gsaviColor[gsavi > 0.40] = [0, 94, 0]
        gsaviColor[gsavi > 0.50] = [1, 59, 0]
        gsaviColor[gsavi > 0.60] = [0, 9, 0]
        gsaviColor[gsavi < 0.00] = [128, 128, 128]
        gsaviColor[gsavi < -0.05] = [96, 96, 96]
        gsaviColor[gsavi < -0.25] = [64, 64, 64]
        gsaviColor[gsavi < -0.50] = [32, 32, 32]
        return gsaviNorm3, gsaviColor

    # MCARI (Modified Chlorophyll Absorption Ratio Index)
    def mcariCalculator(self, b1, b4, b5):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # MCARI = ((R700 - R670) - 0.2 * (R700 - R550 )) * (R700 / R670)
        # Change type to float32
        b1f = b1.astype(np.float32)
        b4f = b4.astype(np.float32)
        b5f = b5.astype(np.float32)
        # Perform the calculations of the formula
        mcari = np.multiply(np.subtract(np.subtract(b5f, b4f), np.multiply(
            0.2, np.subtract(b5f, b1f))), np.divide(b5f, b4f))
        return mcari

    # MSR (Modified Simple Ratio)
    def msrCalculator(self, b3, b6):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # MSR = (NIR/RED - 1) / (sqrt(NIR/RED) + 1)
        # Change type to float32
        b3f = b3.astype(np.float32)
        b6f = b6.astype(np.float32)
        # Perform the calculations of the formula (MSR values from -1.0 to 1.0)
        msr = np.divide(np.subtract(np.divide(b6f, b3f), 1),
                        np.add(np.sqrt(np.divide(b6f, b3f)), 1))
        # Normalized MSR values from 0.0 to 1.0
        msrNorm1 = np.add(np.multiply(msr, 0.5), 0.5)
        # Normalized MSR values from 0.0 to 255.0
        msrNorm2 = np.multiply(msrNorm1, 255)
        # Normalized MSR values to export integer values
        msrNorm3 = msrNorm2.astype(np.uint8)
        # Colors for colormapping RGB
        msrColor = np.zeros((339, 426, 3), np.uint8)

        # Colors for color-mapping in RGB palette
        # MSR coloring for different materials
        # Soil, vegetation and other materials respectievly
        # The colors are BGR not RGB
        msrColor[msr >= 0.00] = [189, 233, 234]
        msrColor[msr > 0.05] = [148, 211, 215]
        msrColor[msr > 0.10] = [119, 189, 202]
        msrColor[msr > 0.15] = [77, 175, 175]
        msrColor[msr > 0.20] = [5, 169, 128]
        msrColor[msr > 0.30] = [0, 127, 12]
        msrColor[msr > 0.40] = [0, 94, 0]
        msrColor[msr > 0.50] = [1, 59, 0]
        msrColor[msr > 0.60] = [0, 9, 0]
        msrColor[msr < 0.00] = [128, 128, 128]
        msrColor[msr < -0.05] = [96, 96, 96]
        msrColor[msr < -0.25] = [64, 64, 64]
        msrColor[msr < -0.50] = [32, 32, 32]
        return msrNorm3, msrColor

    # Calculate TVI (Triangular Vegetation Index)
    # Calculate MTVI1 (Modified Triangular Vegetation Index 1)
    # Calculate MTVI2 (Modified Triangular Vegetation Index 2)
    def tviCalculator(self, b1, b3, b6, b4, b7):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        # Change type to float32
        # GREEN (green band 1 (560nm) is not accurate needs to be approximately 510 nm for real green band)
        b1f = b1.astype(np.float32)
        # RED
        b3f = b3.astype(np.float32)
        # NIR
        b6f = b6.astype(np.float32)
        # Band 4 (670 nm)
        b4f = b4.astype(np.float32)
        # Band 7 (791 nm)
        b7f = b7.astype(np.float32)
        # TVI = 0.5 * (120 * (NIR - GREEN) - 200 * (RED - GREEN))
        tvi = np.multiply(0.5, np.subtract(np.multiply(
            120, np.subtract(b6f, b1f)), np.multiply(200, np.subtract(b3f, b1f))))
        # MTVI1 = 1.2 * (1.2 * (R800 - R550) - 2.5 * (R670 - R550))
        mtvi1 = np.multiply(1.2, np.subtract(np.multiply(
            1.2, np.subtract(b7f, b1f)), np.multiply(2.5, np.subtract(b4f, b1f))))
        # MTVI2 = (1.5 * (1.2 * (R800 - R550) - 2.5 * (R670 - R550)))/ (sqrt((2 * R800 + 1) ^ 2 - (6 * R800 - 5 * sqrt(R670)) - 0.5))
        mtvi2 = np.divide(np.multiply(1.5, np.subtract(np.multiply(1.2, np.subtract(b7f, b1f)), np.multiply(2.5, np.subtract(b4f, b1f)))), np.sqrt(
            np.subtract(np.subtract(np.square(np.add(np.multiply(2, b7f), 1)), np.subtract(np.multiply(6, b7f), np.multiply(5, np.sqrt(b4f)))), 0.5)))
        # Normalized MTVI2 values from 0.0 to 1.0
        mtvi2Norm1 = np.add(np.multiply(mtvi2, 0.5), 0.5)
        # Normalized MTVI2 values from 0.0 to 255.0
        mtvi2Norm2 = np.multiply(mtvi2Norm1, 255)
        # Normalized MTVI2 values to export integer values
        mtvi2Norm3 = mtvi2Norm2.astype(np.uint8)
        return tvi, mtvi1, mtvi2Norm3

    # Image segmentation
    def segmentation(self, image):
        # Thresholding with OTSU
        _, segImage = cv2.threshold(
            image, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        # Erosion removes noise
        erosionSize = 2
        erosionType = cv2.MORPH_ELLIPSE
        el2 = cv2.getStructuringElement(
            erosionType, (2*erosionSize + 1, 2*erosionSize+1), (erosionSize, erosionSize))
        erodedImage = cv2.erode(segImage, el2)
        # Dilation fills holes of the region of interest and expands it
        dilatationSize = 3
        dilatationType = cv2.MORPH_ELLIPSE
        el1 = cv2.getStructuringElement(
            dilatationType, (2*dilatationSize + 1, 2*dilatationSize+1), (dilatationSize, dilatationSize))
        erdImage = cv2.dilate(erodedImage, el1)
        # Return 2 segmented images
        return erdImage, segImage

    # Display coefficients
    def printCrosstalkCoefficients(self):
        for i in range(9):
            for j in range(9):
                print(str(self.wCoefCrossTalk[i][j]) + ", ", end='')
            print("")
        print("")

    # Crop selected pixels and calculates the white reference coefficients
    def whiteReferenceCalculator(self, rawImage):
        # For white balance it has being followed the equation [whiteBalance = 255 / average of the pixels in the selected area for every band]

        # Take the size of the selected area (rows)
        sizeR = self.positions[3] - self.positions[1] + 1
        # Take the starting point of the selected area (rows)
        startR = self.positions[1] - 1
        # Take the ending point of the selected area (rows)
        endR = startR + sizeR
        # Take the size of the selected area (columns)
        sizeC = self.positions[2] - self.positions[0] + 1
        # Take the starting point of the selected area (columns)
        startC = self.positions[0] - 1
        # Take the ending point of the selected area (columns)

        endC = startC + sizeC
        if (self.positions[4] == 1) and (sizeR > 2 and sizeC > 2):
            self.positions[4] = -1  # Checks if the state of the area selection
            if ((self.positions[0] < self.positions[2]) and (self.positions[1] < self.positions[3])):
                pixelSum = [0, 0, 0, 0, 0, 0, 0, 0, 0]
                pixelCount = [0, 0, 0, 0, 0, 0, 0, 0, 0]
                print("r: " + str(sizeR) + " c: " + str(sizeC))
                print("-------------------------------------------------")
                print("Row start: from " + str(startR) + " to " + str(endR))
                print("Column start: from " + str(startC) + " to " + str(endC))
                for i in range(startR, endR):
                    for j in range(startC, endC):
                        if i % 3 == 0:
                            if j % 3 == 0:
                                pixelSum[0] += rawImage[i, j]
                                pixelCount[0] += 1
                                print("Pixel 1: " + str(rawImage[i, j]))
                            elif j % 3 == 1:
                                pixelSum[1] += rawImage[i, j]
                                pixelCount[1] += 1
                                print("Pixel 2: " + str(rawImage[i, j]))
                            else:
                                pixelSum[2] += rawImage[i, j]
                                pixelCount[2] += 1
                                print("Pixel 3: " + str(rawImage[i, j]))
                        elif i % 3 == 1:
                            if j % 3 == 0:
                                pixelSum[3] += rawImage[i, j]
                                pixelCount[3] += 1
                                print("Pixel 4: " + str(rawImage[i, j]))
                            elif j % 3 == 1:
                                pixelSum[4] += rawImage[i, j]
                                pixelCount[4] += 1
                                print("Pixel 5: " + str(rawImage[i, j]))
                            else:
                                pixelSum[5] += rawImage[i, j]
                                pixelCount[5] += 1
                                print("Pixel 6: " + str(rawImage[i, j]))
                        else:
                            if j % 3 == 0:
                                pixelSum[6] += rawImage[i, j]
                                pixelCount[6] += 1
                                print("Pixel 7: " + str(rawImage[i, j]))
                            elif j % 3 == 1:
                                pixelSum[7] += rawImage[i, j]
                                pixelCount[7] += 1
                                print("Pixel 8: " + str(rawImage[i, j]))
                            else:
                                pixelSum[8] += rawImage[i, j]
                                pixelCount[8] += 1
                                print("Pixel 9: " + str(rawImage[i, j]))
                print("-------------------------------------------------")
                print("Sum: " + str(pixelSum[0]) +
                      " TP: " + str(pixelCount[0]))
                print("Sum: " + str(pixelSum[1]) +
                      " TP: " + str(pixelCount[1]))
                print("Sum: " + str(pixelSum[2]) +
                      " TP: " + str(pixelCount[2]))
                print("Sum: " + str(pixelSum[3]) +
                      " TP: " + str(pixelCount[3]))
                print("Sum: " + str(pixelSum[4]) +
                      " TP: " + str(pixelCount[4]))
                print("Sum: " + str(pixelSum[5]) +
                      " TP: " + str(pixelCount[5]))
                print("Sum: " + str(pixelSum[6]) +
                      " TP: " + str(pixelCount[6]))
                print("Sum: " + str(pixelSum[7]) +
                      " TP: " + str(pixelCount[7]))
                print("Sum: " + str(pixelSum[8]) +
                      " TP: " + str(pixelCount[8]))
                print("-------------------------------------------------")
                for i in range(9):
                    result = 1
                    try:
                        result = 255 / float((pixelSum[i] / pixelCount[i]))
                    except ZeroDivisionError:
                        result = 1
                    self.whiteReferenceCoefficients[i] = result
                    print("CO: " + str(self.whiteReferenceCoefficients[i]))
                print("-------------------------------------------------")
                self.saveWhiteReference()
            else:
                print("Start from top left to bottom right.")

    # Enable/disable white reference and draw recthange for the selected area
    def setWhiteReference(self, rawImage, enable):
        if enable:
            rgb = cv2.cvtColor(rawImage, cv2.COLOR_GRAY2RGB)
            if (self.positions[0] >= 0) and (self.positions[1] >= 0) and (self.positions[3] >= 0) and (self.positions[3] >= 0):
                cv2.rectangle(rgb, (self.positions[0], self.positions[1]), (
                    self.positions[2], self.positions[3]), (0, 0, 255), 3, 8, 0)
                self.whiteReferenceCalculator(rawImage)
            # Display image with colored rectangle
            self.displayImage(rgb, "Raw Image")

    # Load white reference coefficients
    def loadWhiteReference(self):
        fs = cv2.FileStorage(self.WR_PATH, cv2.FILE_STORAGE_READ)
        data = fs.getNode("whiteReferenceCoefficients").mat()
        fs.release()
        if data is not None:
            self.whiteReferenceCoefficients = data.flatten()
        else:
            print("Could not retrieve white reference coefficients. Defaults are set.")
            self.whiteReferenceCoefficients = [
                1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

    # Load Manufacturer Parameters
    def loadManufacturerParameters(self):
        fs = cv2.FileStorage(self.MP_PATH, cv2.FILE_STORAGE_READ)
        self.cameraManufacturerSN = fs.getNode("manufacturerSN").string()
        self.cameraSN = fs.getNode("siliosSN").string()
        self.cameraReference = fs.getNode("reference").string()
        self.wCoefCrossTalk = fs.getNode(
            "crosstalkCorrectionCoefficients").mat()
        fs.release()

    # Save white reference coefficients
    def saveWhiteReference(self):
        if(self.whiteReferenceCoefficients is not None):
            print("White reference coefficients saved.")
            print(self.whiteReferenceCoefficients)
            fs = cv2.FileStorage(self.WR_PATH, cv2.FILE_STORAGE_WRITE)
            fs.write("whiteReferenceCoefficients", np.array(
                self.whiteReferenceCoefficients))
            fs.release
            print("-------------------------------------------------")
        else:
            print("No white reference coefficients are available.")

    # Compute flat-field correction that allows you to homogenize the background
    def flatFieldCorrection(self, rawImage):
        # Ignore warnings (comment the lines below when debugging)
        np.seterr(divide='ignore', invalid='ignore')
        m = 1024.0
        n = 1280.0
        # Change type to float32
        Ff = self.F.astype(np.float32)
        Df = self.D.astype(np.float32)
        rawImagef = rawImage.astype(np.float32)
        # Perform the calculations of the formula
        P = (np.subtract(rawImagef, Df) / np.subtract(Ff, Df)) * \
            float(1.0/(m*n)) * np.sum(np.subtract(Ff, Df))
        # Normalize value higher than 255 and lower than 0
        P[P > 255.0] = 255.0
        P[P < 0.0] = 0.0
        # Change type back to uint8
        finalP = P.astype(np.uint8)
        return finalP

    # Reset white reference area positions
    def resetPositions(self):
        for i in range(5):
            self.positions[i] = -1

    # Keyboard listener for predefined cases
    def setOperation(self, key, rawImage):
        if key == 99 or key == 67:  # Keyboard button <c or C>
            if not self.buttonTriggers[0]:
                print("Crosstalk Correction is on.")
                self.buttonTriggers[0] = True
            else:
                print("Crosstalk Correction is off.")
                self.buttonTriggers[0] = False
        elif key == 101 or key == 69:  # Keyboard button <e or E>
            if not self.buttonTriggers[1]:
                print("Flat-field Correction is on.")
                self.buttonTriggers[1] = True
            else:
                print("Flat-field Correction is off.")
                self.buttonTriggers[1] = False
        elif key == 102 or key == 70:  # Keyboard button <f or F>
            if not self.buttonTriggers[2]:
                print("Flat-field image capture is on.")
                self.buttonTriggers[2] = True
                self.F = rawImage
            else:
                print("Flat-field image capture is off.")
                self.buttonTriggers[2] = False
        elif key == 100 or key == 68:  # Keyboard button <d or D>
            if not self.buttonTriggers[3]:
                print("Dark-field image capture is on.")
                self.buttonTriggers[3] = True
                self.D = rawImage
            else:
                print("Dark-field image capture is off.")
                self.buttonTriggers[3] = False
        elif key == 119 or key == 87:  # Keyboard button <w or W>
            if not self.buttonTriggers[4]:
                print("White Reference is on.")
                self.resetPositions()
                self.buttonTriggers[4] = True
            else:
                print("White Reference is off.")
                self.buttonTriggers[4] = False
        elif key == 110 or key == 78:  # Keyboard button <n or N>
            if not self.buttonTriggers[5]:
                print("Display Indexes is on.")
                self.buttonTriggers[5] = True
            else:
                print("Display Indexes is off.")
                self.buttonTriggers[5] = False
        elif key == 98 or key == 66:  # Keyboard button <b or B>
            if not self.buttonTriggers[6]:
                print("Display bands is on.")
                self.buttonTriggers[6] = True
            else:
                print("Display bands is off.")
                self.buttonTriggers[6] = False
        elif key == 114 or key == 82:  # Keyboard button <r or R>
            print("White reference values have reseted.")
            self.whiteReferenceCoefficients = [
                1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
            self.BEST_HOMOGRAPHY = []
            self.MAX_MATCHES = 0
            self.MIN_DIFF = 255
            self.saveWhiteReference()
        elif key == 104 or key == 72:   # Keyboard button <h or H>
            self.saveHomography()
        elif key == 27:
            sys.exit("Shutted down by the user.")

    # Merge all bands in a single image
    def mergeBands(self, images):
        # Create 1278x1017 matrix for window
        # Copy small images into a big matrix, row by row and then column by column
        # From Band 1 to Band 8 - From lower wavelength to higher wavelength - Band 9 = Panchromaic filtered band

        #   Color codes as descibed in the documentation.
        #       Color code 0 - Band 1: Pixel images[2] (Lowest wavelenght filter)
        #       Color code 1 - Band 2: Pixel images[5]
        #       Color code 2 - Band 3: Pixel images[4]
        #       Color code 3 - Band 4: Pixel images[3]
        #       Color code 4 - Band 5: Pixel images[0]
        #       Color code 5 - Band 6: Pixel images[6]
        #       Color code 6 - Band 7: Pixel images[7]
        #       Color code 7 - Band 8: Pixel images[8] (Highest wavelenght filter)
        #       Color code 8 - Band 9: Pixel images[1] (Panchromatic filter)

        row1 = np.hstack((images[8], images[2], images[5]))
        row2 = np.hstack((images[7], images[1], images[4]))
        row3 = np.hstack((images[6], images[0], images[3]))
        allBands = np.vstack((row1, row2, row3))
        return allBands

    # Display raw image and info messages
    def dispalyRawImage(self, rawIMageIN):
        rawImage = rawIMageIN.copy()
        cv2.putText(rawImage, "Use keyboard buttons c, e, f, d, w.", (10, 915),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[0]):
            cv2.putText(rawImage, "Crosstalk Correction is on.", (10, 930),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "Crosstalk Correction is off.", (10, 930),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[1]):
            cv2.putText(rawImage, "Flat-field Correction is on.", (10, 945),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "Flat-field Correction is off.", (10, 945),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[2]):
            cv2.putText(rawImage, "Flat-field image capture is on.", (10, 960),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "Flat-field image capture is off.", (10, 960),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[3]):
            cv2.putText(rawImage, "Dark-field image capture is on.", (10, 975),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "Dark-field image capture is off.", (10, 975),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[4]):
            cv2.putText(rawImage, "White Reference is on.", (10, 990),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "White Reference is off.", (10, 990),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        if (self.buttonTriggers[5]):
            cv2.putText(rawImage, "Display Indexes is on.", (10, 1005),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(rawImage, "Display Indexes is off.", (10, 1005),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        self.displayImage(rawImage, "Raw Image")

    def featureRegistrator(self, im1, im2BGR, im3):
        # BGR channel splitting and acquire only RED channel
        im2 = copy.deepcopy(im2BGR[:, :, 2])
        # The estimated homography will be calculated
        h = self.computeHomographyFeatures(im1, im2)
        # Check if homography matrix exists
        if(h is None):
            r1 = np.zeros((1017, 1278, 3), np.uint8)
            r2 = np.zeros((1017, 1278), np.uint8)
        else:
            r1 = cv2.warpPerspective(im2BGR, np.asarray(h), (1278, 1017))
            r2 = cv2.warpPerspective(im3, np.asarray(h), (1278, 1017))
        if(len(self.BEST_HOMOGRAPHY) == 0):
            r3 = np.zeros((1017, 1278, 3), np.uint8)
            r4 = np.zeros((1017, 1278), np.uint8)
        else:
            r3 = cv2.warpPerspective(im2BGR, np.asarray(
                self.BEST_HOMOGRAPHY), (1278, 1017))
            r4 = cv2.warpPerspective(im3, np.asarray(
                self.BEST_HOMOGRAPHY), (1278, 1017))
        vis1 = np.concatenate((r1, r3), axis=1)
        vis2 = np.concatenate((r2, r4), axis=1)
        # Display aligned images
        cv2.namedWindow(
            "Aligned kinect RGB image (Real time - Best result)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(
            "Aligned kinect RGB image (Real time - Best result)", 1000, 400)
        cv2.imshow(
            "Aligned kinect RGB image (Real time - Best result)", vis1)

        cv2.namedWindow(
            "Aligned kinect depth image (Real time - Best result)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(
            "Aligned kinect depth image (Real time - Best result)", 1000, 400)
        cv2.imshow(
            "Aligned kinect depth image (Real time - Best result)", vis2)

    # Find homography matrix with feature matching. More: https://docs.opencv.org/master/dc/dc3/tutorial_py_matcher.html
    def computeHomographyFeatures(self, img1, img2):
        # Detect ORB features and compute descriptors
        orb = cv2.ORB_create(self.MAX_FEATURES)
        keypoints1, descriptors1 = orb.detectAndCompute(img1, None)
        keypoints2, descriptors2 = orb.detectAndCompute(img2, None)

        # Match features with Brute-Force Matcher
        matcher = cv2.DescriptorMatcher_create(
            cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
        matches = matcher.match(descriptors1, descriptors2, None)

        # Sort matches by DMatch.distance (Distance between descriptors. The lower, the better it is.)
        matches.sort(key=lambda x: x.distance, reverse=False)

        # Remove not so good matches
        numGoodMatches = int(len(matches) * self.GOOD_MATCH_PERCENT)
        matches = matches[:numGoodMatches]

        # Draw top matches 1/2
        imMatches = cv2.drawMatches(
            img1, keypoints1, img2, keypoints2, matches, None)
        cv2.putText(imMatches, "Detected features (left image): " + str(len(keypoints1)),
                    (10, 800), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(imMatches, "Detected features (right image): " + str(len(keypoints2)),
                    (10, 850), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
        # Set a threshold of acceptable number of features
        if (numGoodMatches >= (self.MAX_FEATURES*0.04)):
            # Draw top matches 2/2
            cv2.putText(imMatches, "Matches between the images: " + str(numGoodMatches),
                        (10, 900), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(imMatches, "Matches with min difference: " + str(self.MAX_MATCHES),
                        (10, 950), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(imMatches, "Min captured difference: " + str(self.MIN_DIFF),
                        (10, 1000), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.namedWindow("Matches", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Matches", 1000, 400)
            cv2.imshow("Matches", imMatches)

            # Extract location of good matches
            points1 = np.zeros((len(matches), 2), dtype=np.float32)
            points2 = np.zeros((len(matches), 2), dtype=np.float32)

            for i, match in enumerate(matches):
                points1[i, :] = keypoints1[match.queryIdx].pt
                points2[i, :] = keypoints2[match.trainIdx].pt

            # Find homography with RANSAC method (finds a perspective transformation between two planes)
            h, _ = cv2.findHomography(points2, points1, cv2.RANSAC)
            if h is not None:
                # Compute difference between images and the mean of pixels
                img2New = cv2.warpPerspective(
                    img2, np.asarray(h), (1278, 1017))
                subResult = cv2.subtract(img1, img2New)
                tempVal = cv2.mean(subResult)
                meanResult = tempVal[0]
                # Keep the homography matrix with the most matches and minimun difference
                if meanResult < self.MIN_DIFF:
                    self.MAX_MATCHES = numGoodMatches
                    self.MIN_DIFF = meanResult
                    self.BEST_HOMOGRAPHY = h
                # Dispaly difference between multispectral image and kinect image
                cv2.putText(subResult, "Difference: " + str(meanResult),
                            (10, 1000), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.namedWindow(
                    "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(
                    "Difference between multispectral image and kinect image", 400, 400)
                cv2.imshow(
                    "Difference between multispectral image and kinect image", subResult)
                # Return an acceptable only homography matrix
                if meanResult < 20:
                    return h
                else:
                    return None
            else:
                # Clear differences display
                subResult = np.zeros((1017, 1278), np.uint8)
                subResult[:] = 255
                cv2.namedWindow(
                    "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(
                    "Difference between multispectral image and kinect image", 400, 400)
                cv2.imshow(
                    "Difference between multispectral image and kinect image", subResult)
                return None
        else:
            # Draw top matches 2/2
            cv2.putText(imMatches, "Matches between the images: " + str(numGoodMatches) + " (not enough matches)",
                        (10, 900), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(imMatches, "Matches with min difference: " + str(self.MAX_MATCHES),
                        (10, 950), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(imMatches, "Min captured difference: " + str(self.MIN_DIFF),
                        (10, 1000), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.namedWindow("Matches", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Matches", 1000, 400)
            cv2.imshow("Matches", imMatches)
            # Clear differences display
            subResult = np.zeros((1017, 1278), np.uint8)
            subResult[:] = 255
            cv2.namedWindow(
                "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
            cv2.resizeWindow(
                "Difference between multispectral image and kinect image", 400, 400)
            cv2.imshow(
                "Difference between multispectral image and kinect image", subResult)
            return None

    def cornerRegistrator(self, im1, im2BGR, im3):
        # BGR channel splitting and acquire only RED channel
        im2 = copy.deepcopy(im2BGR[:, :, 2])
        # The estimated homography will be calculated
        h = self.computeHomographyCorners(im1, im2)
        # Check if homography matrix exists
        if(h is None):
            r1 = np.zeros((1017, 1278, 3), np.uint8)
            r2 = np.zeros((1017, 1278), np.uint8)
        else:
            r1 = cv2.warpPerspective(im2BGR, np.asarray(h), (1278, 1017))
            r2 = cv2.warpPerspective(im3, np.asarray(h), (1278, 1017))
        if(len(self.BEST_HOMOGRAPHY) == 0):
            r3 = np.zeros((1017, 1278, 3), np.uint8)
            r4 = np.zeros((1017, 1278), np.uint8)
        else:
            r3 = cv2.warpPerspective(im2BGR, np.asarray(
                self.BEST_HOMOGRAPHY), (1278, 1017))
            r4 = cv2.warpPerspective(im3, np.asarray(
                self.BEST_HOMOGRAPHY), (1278, 1017))
        vis1 = np.concatenate((r1, r3), axis=1)
        vis2 = np.concatenate((r2, r4), axis=1)
        # Display aligned images
        cv2.namedWindow(
            "Aligned kinect RGB image (Real time - Best result)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(
            "Aligned kinect RGB image (Real time - Best result)", 1000, 400)
        cv2.imshow(
            "Aligned kinect RGB image (Real time - Best result)", vis1)

        cv2.namedWindow(
            "Aligned kinect depth image (Real time - Best result)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(
            "Aligned kinect depth image (Real time - Best result)", 1000, 400)
        cv2.imshow(
            "Aligned kinect depth image (Real time - Best result)", vis2)

    # Find homography matrix with chessboard corners. More: https://docs.opencv.org/master/dc/dc3/tutorial_py_matcher.html
    def computeHomographyCorners(self, im1, im2):
        # Find chessboard corners
        # The function requires white space (like a square-thick border,
        # the wider the better) around the board to make the detection more robust in various environments.
        # Otherwise, if there is no border and the background is dark,
        # the outer black squares cannot be segmented properly and so the square grouping and ordering algorithm fails.
        ret1, corners1 = cv2.findChessboardCorners(
            im1, self.patternsize, None, cv2.CALIB_CB_FAST_CHECK)
        ret2, corners2 = cv2.findChessboardCorners(
            im2, self.patternsize, None, cv2.CALIB_CB_FAST_CHECK)
        if ret1 == True and ret2 == True:
            #  Determine corners positions more accurately
            c1 = cv2.cornerSubPix(
                im1, corners1, (11, 11), (-1, -1), self.criteria)
            c2 = cv2.cornerSubPix(
                im2, corners2, (11, 11), (-1, -1), self.criteria)

            # Draw the corners
            img1 = im1.copy()
            img2 = im2.copy()
            cv2.drawChessboardCorners(
                img1, self.patternsize, c1, ret1)
            cv2.drawChessboardCorners(
                img2, self.patternsize, c2, ret2)

            # Resize multispectral image to fit
            img1New = np.zeros((1080, 1920), np.uint8)
            img1New[31:1048, 321:1599] = img1
            # Put text messages multispectral image and kinect image with chessboard
            cv2.putText(img1New, "Min captured difference: " + str(self.MIN_DIFF),
                        (10, 950), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(img1New, "Chessboard detected: " + str(ret1), (10, 1000),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(img2, "Chessboard detected: " + str(ret2), (10, 1000),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            # Merge multispectral image and kinect image with chessboard
            vis1 = np.concatenate((img1New, img2), axis=1)
            # Dispaly multispectral image and kinect image with chessboard
            cv2.namedWindow(
                "Multispectral image - Kinect image", cv2.WINDOW_NORMAL)
            cv2.resizeWindow(
                "Multispectral image - Kinect image", 1000, 400)
            cv2.imshow(
                "Multispectral image - Kinect image", vis1)

            # Find homography with RANSAC method (finds a perspective transformation between two planes)
            h, _ = cv2.findHomography(c2, c1, cv2.RANSAC)

            if (h is not None):
                # Compute difference between images and the mean of pixels
                im2New = cv2.warpPerspective(im2, np.asarray(
                    h), (self.RAW_WIDTH, self.RAW_HEIGHT))
                subResult = cv2.subtract(im1, im2New)
                tempVal = cv2.mean(subResult)
                meanResult = tempVal[0]
                # Keep the homography matrix with the most matches and minimun difference
                if meanResult < self.MIN_DIFF:
                    self.MIN_DIFF = meanResult
                    self.BEST_HOMOGRAPHY = h
                # Dispaly difference between multispectral image and kinect image
                cv2.putText(subResult, "Difference: " + str(meanResult),
                            (10, 1000), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.namedWindow(
                    "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(
                    "Difference between multispectral image and kinect image", 400, 400)
                cv2.imshow(
                    "Difference between multispectral image and kinect image", subResult)
                # Return an acceptable only homography matrix
                if meanResult < 20:
                    return h
                else:
                    return None
            else:
                # Clear differences display
                subResult = np.zeros(
                    (self.RAW_HEIGHT, self.RAW_WIDTH), np.uint8)
                subResult[:] = 255
                cv2.namedWindow(
                    "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
                cv2.resizeWindow(
                    "Difference between multispectral image and kinect image", 400, 400)
                cv2.imshow(
                    "Difference between multispectral image and kinect image", subResult)
                return None
        else:
            # Resize multispectral image to fit
            im1New = np.zeros((1080, 1920), np.uint8)
            im1New[31:1048, 321:1599] = im1
            # Put text messages multispectral image and kinect image
            cv2.putText(im1New, "Min captured difference: " + str(self.MIN_DIFF),
                        (10, 950), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(im1New, "Chessboard detected: " + str(ret1), (10, 1000),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(im2, "Chessboard detected: " + str(ret2), (10, 1000),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            # Merge multispectral image and kinect image
            vis1 = np.concatenate((im1New, im2), axis=1)
            # Dispaly multispectral image and kinect image
            cv2.namedWindow(
                "Multispectral image - Kinect image", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Multispectral image - Kinect image", 1000, 400)
            cv2.imshow("Multispectral image - Kinect image", vis1)
            # Clear differences display
            subResult = np.zeros(
                (self.RAW_HEIGHT, self.RAW_WIDTH), np.uint8)
            subResult[:] = 255
            cv2.namedWindow(
                "Difference between multispectral image and kinect image", cv2.WINDOW_NORMAL)
            cv2.resizeWindow(
                "Difference between multispectral image and kinect image", 400, 400)
            cv2.imshow(
                "Difference between multispectral image and kinect image", subResult)
            return None

    # Print and save matrix
    def saveHomography(self):
        if(self.BEST_HOMOGRAPHY is not None):
            print(
                "-------------Homography matrix saved to homography.yaml-------------")
            print(self.BEST_HOMOGRAPHY)
            fs = cv2.FileStorage(self.HF_PATH, cv2.FILE_STORAGE_WRITE)
            fs.write("homographyMatrix", self.BEST_HOMOGRAPHY)
            fs.release
            print("----------------------End---------------------------\n")
        else:
            print("No homography matrix is available.")


def main():
    BandSeparator()


if __name__ == "__main__":
    main()
