import SwiftUI
import AVFoundation
import MediaPlayer
import EventKit
import Combine
import Speech

// --- 1. データ型の定義 ---

struct ChatMessage: Codable {
    let role: String
    let content: String
}

struct ServerResponse: Codable {
    let user_text: String
    let ai_text: String
    let audio_data: String 
    let swift_action: String? 
    let parameters: [String: String]?
}

final class ConversationQueue<T>: ObservableObject {
    private var elements: [T] = []
    let maxCapacity: Int
    
    init(maxCapacity: Int) {
        self.maxCapacity = maxCapacity
    }
    
    func enqueue(_ element: T) {
        elements.append(element)
        if elements.count > maxCapacity {
            elements.removeFirst()
        }
    }
    
    var allElements: [T] {
        return elements
    }
}

class MusicPlayerHandler {
    private static let musicPlayer = MPMusicPlayerController.systemMusicPlayer
    
    static func isPlayingMusic() -> Bool {
        return musicPlayer.playbackState == .playing
    }
    
    static func setUpMusicNotifer(){
        musicPlayer.beginGeneratingPlaybackNotifications()
    }
    
    static func shutdownMusicNotifier(){
        musicPlayer.endGeneratingPlaybackNotifications()
    }
    
    static func replayMusic() {
        if musicPlayer.playbackState == .paused {
            musicPlayer.play()
        }
    }
    
    static func stopMusic() {
        if musicPlayer.playbackState == .playing {
            musicPlayer.pause()
        }
    }
    
    static func playMusic(parameters: [String: String]) {        
        let query = MPMediaQuery.songs()
        musicPlayer.setQueue(with: query)
        musicPlayer.play()
    }
}

// --- ArkanoEngine ---

class ArkanoEngine: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var status: String = "待機中"
    @Published var isTalking: Bool = false
    @Published var currentDb: Float = -60.0
    @Published var level: Double = 0.0
    @Published var chatHistory = ConversationQueue<ChatMessage>(maxCapacity: 6)
    
    private let audioEngine = AVAudioEngine()
    private var audioPlayer: AVAudioPlayer?
    
    private var silenceCounter: Int = 0
    private let silenceThreshold: Int = 45 
    private let voiceDbThreshold: Float = -25.0
    private var hasDetectedVoice: Bool = false
    
    private var cancellables = Set<AnyCancellable>()
    private let renderURL = URL(string: "https://my-tools-2oz2.onrender.com/voice")!
    
    // --- 修正箇所: iOS 17+ の推奨APIへリプレイス ---
    func bootstrap() {
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        self?.setupAndStart()
                    } else {
                        self?.status = "マイク許可が必要です"
                    }
                }
            }
        } else {
            // iOS 17 未満の旧デバイス用フォールバック
            AVAudioSession.sharedInstance().requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        self?.setupAndStart()
                    } else {
                        self?.status = "マイク許可が必要です"
                    }
                }
            }
        }
    }
    
    private func setupAndStart() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers])
        try? session.setActive(true)
        self.startListening()
        self.setupBargeInObserver()
        MusicPlayerHandler.setUpMusicNotifer()
    }
    
    func startListening() {
        stopAll()
        hasDetectedVoice = false
        status = "聞き取り中..."
        
        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] (buffer, _) in
            self?.analyzeAudio(buffer: buffer)
        }
        
        do {
            try audioEngine.start()
        } catch {
            reboot(after: 2.0)
        }
    }
    
    private func analyzeAudio(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frameLength = Int(buffer.frameLength)
        let channelDataArray = Array(UnsafeBufferPointer(start: channelData, count: frameLength))
        
        let sum = channelDataArray.reduce(0) { $0 + $1 * $1 }
        let rms = sqrt(sum / Float(frameLength))
        let avgPower = 20 * log10(max(rms, 0.000001))
        let db = avgPower.isFinite ? avgPower : -60.0
        
        DispatchQueue.main.async {
            self.currentDb = db
            withAnimation(.linear(duration: 0.1)) {
                self.level = Double(max(0, (db + 60) / 60))
            }
            
            if db >= self.voiceDbThreshold {
                self.isTalking = true
                self.silenceCounter = 0
                self.hasDetectedVoice = true
            } else {
                self.isTalking = false
                self.silenceCounter += 1
            }
            
            if self.silenceCounter >= self.silenceThreshold {
                self.finishAndUpload(buffer: buffer)
            }
        }
    }
    
    private func stopAll() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        if MusicPlayerHandler.isPlayingMusic() {
            MusicPlayerHandler.stopMusic()
        }
        audioPlayer?.stop()
    }
    
    private func setupBargeInObserver() {
        AVAudioSession.sharedInstance().publisher(for: \.isOtherAudioPlaying)
            .sink { [weak self] isOtherPlaying in
                if isOtherPlaying { self?.handleBargeIn() }
            }
            .store(in: &cancellables)
    }
    
    func handleBargeIn() {
        if audioPlayer?.isPlaying == true {
            audioPlayer?.stop()
        }
        stopAll()
        DispatchQueue.main.async {
            self.isTalking = false
            self.hasDetectedVoice = false
            self.startListening()
        }
    }
    
    private func playResponse(data: Data) {
        do {
            status = "発話中..."
            audioPlayer = try AVAudioPlayer(data: data)
            audioPlayer?.delegate = self
            audioPlayer?.play()
            
            if !audioEngine.isRunning {
                try? audioEngine.start()
            }
        } catch {
            startListening()
        }
        
        if !MusicPlayerHandler.isPlayingMusic() {
            MusicPlayerHandler.replayMusic()
        }
    }
    
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async {
            self.startListening()
        }
    }
    
    private func reboot(after seconds: Double) {
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) {
            self.startListening()
        }
    }
    
    private func finishAndUpload(buffer: AVAudioPCMBuffer) {
        if !hasDetectedVoice {
            self.startListening() 
            return
        }
        
        stopAll()
        status = "思考中..."
        
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: renderURL)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        
        if let historyData = try? JSONEncoder().encode(chatHistory.allElements),
           let historyString = String(data: historyData, encoding: .utf8) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"history\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(historyString)\r\n".data(using: .utf8)!)
        }
        
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"input.pcm\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/pcm\r\n\r\n".data(using: .utf8)!)
        body.append(Data(buffer: buffer))
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            DispatchQueue.main.async {
                guard let jsonData = data else {
                    self?.reboot(after: 1.0)
                    return
                }
                do {
                    let res = try JSONDecoder().decode(ServerResponse.self, from: jsonData)
                    self?.chatHistory.enqueue(ChatMessage(role: "user", content: res.user_text))
                    self?.chatHistory.enqueue(ChatMessage(role: "assistant", content: res.ai_text))
                    if let audioBinary = Data(base64Encoded: res.audio_data) {
                        self?.playResponse(data: audioBinary)
                    }
                } catch {
                    self?.reboot(after: 1.0)
                }
            }
        }.resume()
    }
}

extension Data {
    init(buffer: AVAudioPCMBuffer) {
        let audioBuffer = buffer.audioBufferList.pointee.mBuffers
        self.init(bytes: audioBuffer.mData!, count: Int(audioBuffer.mDataByteSize))
    }
}

struct ContentView: View {
    @StateObject private var engine = ArkanoEngine()
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 50) {
                Spacer()
                ZStack {
                    Circle()
                        .stroke(Color.cyan.opacity(0.3), lineWidth: 2)
                        .scaleEffect(engine.isTalking || engine.status == "発話中..." ? 1.5 : 1.0)
                        .opacity(engine.isTalking || engine.status == "発話中..." ? 0.0 : 0.5)
                        .animation(engine.isTalking ? .easeOut(duration: 0.8).repeatForever(autoreverses: false) : .default, value: engine.isTalking)
                    
                    Circle()
                        .fill(engine.status == "発話中..." ? Color.green : (engine.isTalking ? Color.cyan : Color.gray.opacity(0.3)))
                        .frame(width: 140, height: 140)
                        .scaleEffect(0.85 + (engine.level * 0.4))
                }
                
                VStack(spacing: 15) {
                    Text(engine.status)
                        .font(.system(size: 22, weight: .medium, design: .monospaced))
                        .foregroundColor(.white)
                    
                    Text("\(String(format: "%.1f", engine.currentDb)) dB")
                        .font(.system(size: 14, design: .monospaced))
                        .foregroundColor(.gray.opacity(0.6))
                }
                Spacer(); Spacer()
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            engine.bootstrap()
        }
    }
}
