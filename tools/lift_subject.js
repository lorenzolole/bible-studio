// Lifts the main subject out of an image with Apple's Vision framework (macOS 14+), the same
// segmentation behind "Copy Subject" in Photos, and saves it as a PNG with transparency.
// JavaScript for Automation, so it runs without Xcode or compiling:
//
//   osascript -l JavaScript tools/lift_subject.js assets/visuals/painting.jpg assets/figures/figure.png
ObjC.import("Foundation");
ObjC.import("Vision");
ObjC.import("CoreImage");
ObjC.import("CoreGraphics");

function run(argv) {
    if (argv.length !== 2) {
        throw new Error("Usage: osascript -l JavaScript tools/lift_subject.js <input image> <output.png>");
    }
    const cwd = $.NSFileManager.defaultManager.currentDirectoryPath.js;
    const absolute = (p) => (p.startsWith("/") ? p : `${cwd}/${p}`);
    const inputURL = $.NSURL.fileURLWithPath(absolute(argv[0]));
    const outputURL = $.NSURL.fileURLWithPath(absolute(argv[1]));

    const image = $.CIImage.imageWithContentsOfURL(inputURL);
    if (image.isNil()) throw new Error(`Could not read ${argv[0]}`);

    const handler = $.VNImageRequestHandler.alloc.initWithCIImageOptions(image, $.NSDictionary.dictionary);
    const request = $.VNGenerateForegroundInstanceMaskRequest.alloc.init;
    const error = Ref();
    if (!handler.performRequestsError($.NSArray.arrayWithObject(request), error)) {
        throw new Error(`Vision request failed: ${error[0] ? error[0].localizedDescription.js : "unknown"}`);
    }
    if (request.results.isNil() || request.results.count === 0) {
        throw new Error(`No subject found in ${argv[0]}`);
    }

    const observation = request.results.objectAtIndex(0);
    const masked = observation.generateMaskedImageOfInstancesFromRequestHandlerCroppedToInstancesExtentError(
        observation.allInstances, handler, false, error);
    if (!masked) {
        throw new Error(`Could not build the cutout: ${error[0] ? error[0].localizedDescription.js : "unknown"}`);
    }

    const output = $.CIImage.imageWithCVPixelBuffer(masked);
    const context = $.CIContext.context;
    const colorSpace = $.CGColorSpaceCreateWithName($.kCGColorSpaceSRGB);
    const ok = context.writePNGRepresentationOfImageToURLFormatColorSpaceOptionsError(
        output, outputURL, $.kCIFormatRGBA8, colorSpace, $.NSDictionary.dictionary, error);
    if (!ok) {
        throw new Error(`Could not write ${argv[1]}: ${error[0] ? error[0].localizedDescription.js : "unknown"}`);
    }
    return `Saved ${argv[1]} (${output.extent.size.width}x${output.extent.size.height})`;
}
