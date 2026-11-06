// Records this Mac's location to a JSONL file that the Python daemon reads.
//
// This is the one non-Python part of the project. macOS only grants location access to a
// process with a bundle identity, and a Python interpreter doesn't get one, even when it's
// launched from inside an .app.

import AppKit
import CoreLocation

let minSecondsBetweenFixes = 60.0

final class Recorder: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private let logURL: URL
    private var lastWrite = Date.distantPast

    init(logURL: URL) {
        self.logURL = logURL
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func start() {
        manager.requestAlwaysAuthorization()
        manager.startUpdatingLocation()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let fix = locations.last, fix.horizontalAccuracy >= 0 else { return }
        guard fix.timestamp.timeIntervalSince(lastWrite) >= minSecondsBetweenFixes else { return }
        lastWrite = fix.timestamp
        append(fix)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        NSLog("HistoryLocation: \(error)")
    }

    private func append(_ fix: CLLocation) {
        let record: [String: Double] = [
            "ts": fix.timestamp.timeIntervalSince1970,
            "lat": fix.coordinate.latitude,
            "lon": fix.coordinate.longitude,
            "accuracy_m": fix.horizontalAccuracy,
        ]
        guard var line = try? JSONSerialization.data(withJSONObject: record) else { return }
        line.append(0x0A)
        let manager = FileManager.default
        try? manager.createDirectory(
            at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !manager.fileExists(atPath: logURL.path) {
            manager.createFile(atPath: logURL.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: logURL) else { return }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: line)
    }
}

let logURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent(".local/share/history/location.jsonl")
let recorder = Recorder(logURL: logURL)
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
recorder.start()
app.run()
