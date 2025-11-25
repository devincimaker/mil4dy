/**
 * Motion Detector
 *
 * Analyzes video frames to detect motion using background subtraction.
 * Outputs motion percentage (0-100%) representing how much of the frame is moving.
 */

export class MotionDetector {
  constructor(options = {}) {
    // Detection parameters
    this.threshold = options.threshold ?? 25; // Pixel difference threshold
    this.minMotionPixels = options.minMotionPixels ?? 50; // Minimum pixels to count as motion
    this.backgroundAlpha = options.backgroundAlpha ?? 0.05; // Background update rate (0-1)

    // State
    this.background = null;
    this.width = 0;
    this.height = 0;
    this.frameCount = 0;

    // Results
    this.motionPercentage = 0;
    this.motionPixelCount = 0;

    // Callbacks
    this.onMotion = null;

    // Debug canvas (optional)
    this.debugCanvas = null;
    this.debugCtx = null;
  }

  /**
   * Enable debug visualization.
   * @param {HTMLCanvasElement} canvas - Canvas to draw debug info to
   */
  enableDebug(canvas) {
    this.debugCanvas = canvas;
    this.debugCtx = canvas.getContext('2d');
  }

  /**
   * Disable debug visualization.
   */
  disableDebug() {
    this.debugCanvas = null;
    this.debugCtx = null;
  }

  /**
   * Process a video frame and detect motion.
   * @param {Object} frame - Frame data from camera
   * @param {ImageData} frame.imageData - The image data
   * @param {number} frame.width - Frame width
   * @param {number} frame.height - Frame height
   */
  processFrame(frame) {
    const { imageData, width, height } = frame;

    // Initialize or resize background model
    if (
      !this.background ||
      this.width !== width ||
      this.height !== height
    ) {
      this.initBackground(imageData, width, height);
      return { motionPercentage: 0, motionPixelCount: 0 };
    }

    // Convert current frame to grayscale
    const currentGray = this.toGrayscale(imageData.data, width, height);

    // Calculate frame difference from background
    const diff = this.calculateDifference(currentGray);

    // Count motion pixels
    const motionResult = this.countMotionPixels(diff);

    // Update background model slowly
    this.updateBackground(currentGray);

    // Store results
    this.motionPercentage = motionResult.percentage;
    this.motionPixelCount = motionResult.count;
    this.frameCount++;

    // Draw debug visualization if enabled
    if (this.debugCanvas) {
      this.drawDebug(diff, motionResult);
    }

    // Emit callback
    if (this.onMotion) {
      this.onMotion({
        percentage: motionResult.percentage,
        pixelCount: motionResult.count,
        totalPixels: width * height,
        frameNumber: this.frameCount,
      });
    }

    return motionResult;
  }

  /**
   * Initialize the background model from first frame.
   */
  initBackground(imageData, width, height) {
    this.width = width;
    this.height = height;
    this.background = this.toGrayscale(imageData.data, width, height);
    this.frameCount = 0;

    if (this.debugCanvas) {
      this.debugCanvas.width = width;
      this.debugCanvas.height = height;
    }

    console.log(`[MotionDetector] Background initialized: ${width}x${height}`);
  }

  /**
   * Convert RGBA image data to grayscale float array.
   */
  toGrayscale(data, width, height) {
    const gray = new Float32Array(width * height);
    const len = width * height;

    for (let i = 0; i < len; i++) {
      const idx = i * 4;
      // Standard luminance formula
      gray[i] =
        data[idx] * 0.299 + data[idx + 1] * 0.587 + data[idx + 2] * 0.114;
    }

    return gray;
  }

  /**
   * Calculate absolute difference between current frame and background.
   */
  calculateDifference(currentGray) {
    const len = this.width * this.height;
    const diff = new Uint8Array(len);

    for (let i = 0; i < len; i++) {
      diff[i] = Math.abs(currentGray[i] - this.background[i]);
    }

    return diff;
  }

  /**
   * Count pixels exceeding motion threshold.
   */
  countMotionPixels(diff) {
    const len = diff.length;
    let count = 0;

    for (let i = 0; i < len; i++) {
      if (diff[i] > this.threshold) {
        count++;
      }
    }

    // Only count as motion if above minimum
    if (count < this.minMotionPixels) {
      count = 0;
    }

    const percentage = (count / len) * 100;

    return {
      count,
      percentage: Math.min(100, percentage),
    };
  }

  /**
   * Update background model with exponential moving average.
   */
  updateBackground(currentGray) {
    const alpha = this.backgroundAlpha;
    const oneMinusAlpha = 1 - alpha;
    const len = this.background.length;

    for (let i = 0; i < len; i++) {
      this.background[i] =
        oneMinusAlpha * this.background[i] + alpha * currentGray[i];
    }
  }

  /**
   * Draw debug visualization showing motion mask.
   */
  drawDebug(diff, motionResult) {
    if (!this.debugCtx) return;

    const imageData = this.debugCtx.createImageData(this.width, this.height);
    const data = imageData.data;
    const len = diff.length;

    for (let i = 0; i < len; i++) {
      const idx = i * 4;
      const isMotion = diff[i] > this.threshold;

      if (isMotion) {
        // Motion pixels in hot pink
        data[idx] = 255;
        data[idx + 1] = 51;
        data[idx + 2] = 102;
        data[idx + 3] = 255;
      } else {
        // Background in dark gray
        const gray = Math.min(255, diff[i] * 2);
        data[idx] = gray * 0.2;
        data[idx + 1] = gray * 0.2;
        data[idx + 2] = gray * 0.3;
        data[idx + 3] = 255;
      }
    }

    this.debugCtx.putImageData(imageData, 0, 0);

    // Draw motion percentage
    this.debugCtx.fillStyle = '#00ffaa';
    this.debugCtx.font = '14px monospace';
    this.debugCtx.fillText(
      `Motion: ${motionResult.percentage.toFixed(1)}%`,
      8,
      20
    );
  }

  /**
   * Get current motion percentage (0-100).
   */
  getMotionPercentage() {
    return this.motionPercentage;
  }

  /**
   * Reset the background model.
   */
  reset() {
    this.background = null;
    this.frameCount = 0;
    this.motionPercentage = 0;
    this.motionPixelCount = 0;
    console.log('[MotionDetector] Reset');
  }

  /**
   * Adjust detection sensitivity.
   * @param {number} threshold - Lower = more sensitive (10-50 typical)
   */
  setSensitivity(threshold) {
    this.threshold = Math.max(5, Math.min(100, threshold));
    console.log(`[MotionDetector] Threshold set to ${this.threshold}`);
  }
}

