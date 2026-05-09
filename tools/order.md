```
import SwiftUI
import AVFoundation
import MediaPlayer
import Combine
import EventKit

// --- 1. データ型の定義 ---

struct ChatMessage: Codable {
    let role: String    // "user" または "assistant"
    let content: String
}

struct ServerResponse: Codable {
    let user_text: String
    let ai_text: String
    let audio_data: String // Base64文字列
    let swift_action: String? // Appleintent
    let parameters: [String: String]? // 変更: 辞書型(Dictionary)
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

class GuardianEngine: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var status: String = "待機中"
    @Published var isTalking: Bool = false
    @Published var currentDb: Float = -60.0
    @Published var level: Double = 0.0
    
    @Published var chatHistory = ConversationQueue<ChatMessage>(maxCapacity: 6)
    
    private var audioRecorder: AVAudioRecorder?
    private var audioPlayer: AVAudioPlayer?
    private var silenceCounter: Int = 0
    private var timer: Timer?
    
    // --- パラメータ調整 ---
    private let silenceThreshold: Int = 45  // 2.5秒無音で送信
    private let voiceDbThreshold: Float = -30.0
    private var hasDetectedVoice: Bool = false // 声を検知したかどうかのフラグ
    
    // Combineのメモリ管理用
    private var cancellables = Set<AnyCancellable>()
    
    private let renderURL = URL(string: "https://my-tools-2oz2.onrender.com/voice")! 
    
    func bootstrap() {
        AVAudioApplication.requestRecordPermission { granted in
            DispatchQueue.main.async {
                if granted {
                    self.startListening()
                    self.setupBargeInObserver() // 起動時に割り込み監視をセットアップ
                } else {
                    self.status = "マイク許可が必要です"
                }
            }
        }
    }
    
    func startListening() {
        self.stopAll() 
        self.hasDetectedVoice = false // 録音開始時にリセット
        
        let session = AVAudioSession.sharedInstance()
        // 【修正】.mixWithOthersを追加し、ミュージックとマイクを同時に使用できるようにします
        try? session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers])
        try? session.setActive(true)
        
        let docDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let fileURL = docDir.appendingPathComponent("guardian_audio.m4a")
        
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 12000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: fileURL, settings: settings)
            audioRecorder?.isMeteringEnabled = true
            if audioRecorder?.record() == true {
                status = "聞き取り中..."
                self.runMonitoringLoop()
            }
        } catch {
            self.reboot(after: 2.0)
        }
    }
    
    private func runMonitoringLoop() {
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let rec = self.audioRecorder, rec.isRecording else { return }
            
            rec.updateMeters()
            let db = rec.averagePower(forChannel: 0)
            
            DispatchQueue.main.async {
                self.currentDb = db
                
                // UIアニメーション用のレベル計算
                withAnimation(.linear(duration: 0.1)) {
                    self.level = Double(max(0, (db + 60) / 60))
                }
                
                if db > self.voiceDbThreshold {
                    self.isTalking = true
                    self.silenceCounter = 0 
                    self.hasDetectedVoice = true // 声を検知！
                } else {
                    self.isTalking = false
                    self.silenceCounter += 1
                }
                
                if self.silenceCounter >= self.silenceThreshold {
                    self.finishAndUpload()
                }
            }
        }
    }
    
    private func stopAll() {
        timer?.invalidate()
        timer = nil
        audioRecorder?.stop()
        audioPlayer?.stop()
    }
    
    // --- 割り込み検知用の監視スタート --
    private func setupBargeInObserver() {
        AVAudioSession.sharedInstance().publisher(for: \.isOtherAudioPlaying)
            .sink { [weak self] isOtherPlaying in
                if isOtherPlaying {
                    self?.handleBargeIn()
                }
            }
            .store(in: &cancellables)
        MPMusicPlayerController.systemMusicPlayer.beginGeneratingPlaybackNotifications()
        NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)
            .sink { [weak self] notification in
                guard let self = self else { return }
                guard let userInfo = notification.userInfo,
                      let typeValue = userInfo[AVAudioSessionInterruptionTypeKey] as? UInt,
                      let type = AVAudioSession.InterruptionType(rawValue: typeValue) else { return }
                
                if type == .began {
                    self.handleBargeIn()
                }
            }
            .store(in: &cancellables)
    }
    
    // --- 割り込み処理 ---
    func handleBargeIn() {
        if let player = audioPlayer, player.isPlaying {
            player.stop()
        }
        
        // 音声認識や監視用タイマーのリセット
        stopAll()
        
        DispatchQueue.main.async {
            self.status = "割り込み検知..."
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
            
            // 発話中もBarge-in対応の音声チェックを継続させる
            startBargeInMonitoring()
            
            audioPlayer?.play()
        } catch {
            self.startListening()
        }
    }
    
    // 発話中のマイク監視
    private func startBargeInMonitoring() {
        let session = AVAudioSession.sharedInstance()
        // 【修正】.mixWithOthersを追加し、ミュージックが停止しないようにします
        try? session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers])
        try? session.setActive(true)
        
        let docDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let fileURL = docDir.appendingPathComponent("bargein_audio.m4a")
        
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 12000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: fileURL, settings: settings)
            audioRecorder?.isMeteringEnabled = true
            if audioRecorder?.record() == true {
                self.runBargeInMonitoringLoop()
            }
        } catch {
            // エラー時はリスニングへ戻る
            self.reboot(after: 1.0)
        }
    }
    
    private func runBargeInMonitoringLoop() {
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let rec = self.audioRecorder, rec.isRecording else { return }
            
            rec.updateMeters()
            let db = rec.averagePower(forChannel: 0)
            
            DispatchQueue.main.async {
                self.currentDb = db
                // 閾値を超えた場合（発話中の割り込み）
                if db > self.voiceDbThreshold {
                    self.handleBargeIn()
                }
            }
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
    
    func handleIntent(action: String, parameters: [String: String]) {
        switch action {
        case "PlayMusicIntent":
            print("アクション実行: \(action)")
            playMusic(parameters: parameters)
        case "SetReminderIntent":
            print("アクション実行: \(action)")
            setReminder(parameters: parameters)
        default:
            print("該当するアクションはありませんでした: \(action)")
        }
    }
    
    private func playMusic(parameters: [String: String]) {
        let musicPlayer = MPMusicPlayerController.systemMusicPlayer
        musicPlayer.setQueue(with: .songs())
        musicPlayer.play()
    }
    
    private func setReminder(parameters: [String: String]) {
        let eventStore = EKEventStore()
        
        Task {
            do {
                print("[Reminder] 処理を開始します。 parameters: \(parameters)")
                
                if #available(iOS 17.0, *) {
                    try await eventStore.requestFullAccessToReminders()
                } else {
                    try await eventStore.requestAccess(to: .reminder)
                }
                print("[Reminder] アクセス許可を取得しました。")
                
                let reminder = EKReminder(eventStore: eventStore)
                reminder.title = parameters["title"] ?? "新しいリマインダー"
                
                if let targetTime = parameters["target_time"] {
                    reminder.notes = "設定時間: \(targetTime)"
                }
                
                if let calendar = eventStore.defaultCalendarForNewReminders() {
                    reminder.calendar = calendar
                } else if let fallbackCalendar = eventStore.calendars(for: .reminder).first {
                    reminder.calendar = fallbackCalendar
                } else {
                    print("[Reminder] エラー: 有効なカレンダーが見つかりません。")
                    return
                }
                
                try eventStore.save(reminder, commit: true)
                print("[Reminder] 登録が完了しました: \(reminder.title ?? "")")
            } catch {
                print("[Reminder] 追加エラーが発生しました: \(error.localizedDescription)")
            }
        }
    }
    
    private func finishAndUpload() {
        if !hasDetectedVoice {
            print("無音スキップ")
            self.startListening() 
            return
        }
        
        guard let url = audioRecorder?.url else { return }
        self.stopAll()
        
        status = "思考中..."
        
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: renderURL)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30.0 
        
        var body = Data()
        
        if let historyData = try? JSONEncoder().encode(chatHistory.allElements),
           let historyString = String(data: historyData, encoding: .utf8) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"history\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(historyString)\r\n".data(using: .utf8)!)
        }
        
        if let fileData = try? Data(contentsOf: url) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"input.m4a\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: audio/m4a\r\n\r\n".data(using: .utf8)!)
            body.append(fileData)
            body.append("\r\n".data(using: .utf8)!)
        }
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body
        
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            DispatchQueue.main.async {
                if let requestError = error {
                    self?.status = "接続エラー: \(requestError.localizedDescription)"
                    self?.reboot(after: 2.0)
                    return 
                }
                
                guard let jsonData = data else {
                    self?.reboot(after: 1.0)
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(ServerResponse.self, from: jsonData)
                    self?.chatHistory.enqueue(ChatMessage(role: "user", content: response.user_text))
                    self?.chatHistory.enqueue(ChatMessage(role: "assistant", content: response.ai_text))
                    
                    if let audioBinary = Data(base64Encoded: response.audio_data) {
                        self?.playResponse(data: audioBinary)
                    } else {
                        self?.reboot(after: 1.0)
                    }
                    if let action = response.swift_action, !action.isEmpty {
                        self?.handleIntent(action: action, parameters: response.parameters ?? [:])
                    }
                } catch {
                    self?.status = "解析エラー"
                    self?.reboot(after: 1.0)
                }
            }
        }.resume()
    }
}
// --- 4. エージェントの見た目 (View) ---

struct ContentView: View {
    @StateObject private var engine = GuardianEngine()
    
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
                        .animation(.easeOut(duration: 0.8).repeatForever(autoreverses: false), value: engine.isTalking)
                    
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
                
                Spacer()
                Spacer()
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            engine.bootstrap()
        }
    }
}
```

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
                        self?.startListening()
                        self?.setupBargeInObserver()
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
                        self?.startListening()
                        self?.setupBargeInObserver()
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
        self.stopAll() 
        self.hasDetectedVoice = false // 録音開始時にリセット
        
        let session = AVAudioSession.sharedInstance()
        // 【修正】.mixWithOthersを追加し、ミュージックとマイクを同時に使用できるようにします
        try? session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers])
        try? session.setActive(true)
        
        let docDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let fileURL = docDir.appendingPathComponent("guardian_audio.m4a")
        
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 12000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: fileURL, settings: settings)
            audioRecorder?.isMeteringEnabled = true
            if audioRecorder?.record() == true {
                status = "聞き取り中..."
                self.runMonitoringLoop()
            }
        } catch {
            self.reboot(after: 2.0)
        }
    }
    
    private func runMonitoringLoop() {
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let rec = self.audioRecorder, rec.isRecording else { return }
            
            rec.updateMeters()
            let db = rec.averagePower(forChannel: 0)
            
            DispatchQueue.main.async {
                self.currentDb = db
                
                // UIアニメーション用のレベル計算
                withAnimation(.linear(duration: 0.1)) {
                    self.level = Double(max(0, (db + 60) / 60))
                }
                
                if db > self.voiceDbThreshold {
                    self.isTalking = true
                    self.silenceCounter = 0 
                    self.hasDetectedVoice = true // 声を検知！
                } else {
                    self.isTalking = false
                    self.silenceCounter += 1
                }
                
                if self.silenceCounter >= self.silenceThreshold {
                    self.finishAndUpload()
                }
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

python
旧
```
import os
import io
import asyncio
import time
import json
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts
import cgi
from difflib import get_close_matches
#プロンプト

SYSTEM_BASE = "あなたはユーザーの思考を深めるインタビュアーです。"

CONSTRAINTS = """
- 1〜2文で簡潔に話してください。
- オウム返しするより、あなたの意見や感想を述べることに集中してください。
- 相手の話が長くても、最後まで話を聞いてください
"""

BEHAVIOR_LOGIC = """
# 相手の話題に対して、必ず以下のいずれかを行ってください
-「相手が答えやすくなる具体的な質問」
-「独自の視点」から新しい提案

# 相手が明確に以下のキーワードを使ったとき、「本日の会話は以上です。お疲れ様でした。」と一言添えて終了してください。
- 「もう大丈夫」
- 「今日は終わり」

"""

def get_system_prompt():
    return f"{SYSTEM_BASE}\n\n【制約】{CONSTRAINTS}\n\n【思考プロセス】{BEHAVIOR_LOGIC}"
system_prompt = get_system_prompt()
# RAG
"""インメモリDB"""
INTENTS_DB = {
    "playMusic": {
        "summary": "ミュージックアプリで楽曲やプレイリストを再生する",
        "parameters": [
            {
                "name": "song_name",
                "type": "string",
                "description": "再生したい曲名（例: CRICIS）"
            },
            {
                "name": "artist_name",
                "type": "string",
                "description": "再生したいアーティスト名やグループ名（例: acidBlackCherry）"
            },
            {
                "name": "playlist_name",
                "type": "string",
                "description": "再生したいプレイリスト名（例: トップ25）"
            }
        ],
        "usage_example": [
            "音楽をかけて",
            "L'Arc~en~Cielの曲を再生して",
            "リラックスできるプレイリストを流して"
        ],
        "swift_action": "PlayMusicIntent"
    },
    "setReminder": {
        "summary": "リマインダーに予定を追加する",
        "parameters": [
            {
                "name": "title",
                "type": "string",
                "description": "リマインダーの内容やタイトル"
            },
            {
                "name": "target_time",
                "type": "string",
                "description": "リマインダーを設定する日時や時刻（例: 15:00、明日）"
            }
        ],
        "usage_example": [
            "リマインダーに予定を入れて"
        ],
        "swift_action": "SetReminderIntent"
    }
}
class FileUtil:
    @staticmethod
    def temp_file():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        in_file = f"in_{timestamp}.m4a"
        out_file = f"out_{timestamp}.mp3"
        
        return {'in':in_file,'out':out_file}
    @staticmethod
    def rm_f(in_file, out_file):
        # 一時ファイルの削除
        for f in [in_file, out_file]:
            if os.path.exists(f):
                os.remove(f)


# 環境変数の読み込み
load_dotenv()

# クライアントの初期化
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    
    def search_intent(self, query: str) -> dict:
        """インメモリでのあいまい検索処理"""
        keys = list(INTENTS_DB.keys())
        matches = get_close_matches(query, keys, n=1, cutoff=0.3)
        if matches:
            return INTENTS_DB[matches[0]]
        return {}
    
    # 1. ヘルスチェック・ブラウザアクセス用
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Guardian Service is Running".encode('utf-8'))

    # 2. Render等の監視サービス用
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

    # 3. メインの音声・履歴処理
    def do_POST(self):
        if self.path == '/voice':
            try:
                # Multipartデータの解析
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST'}
                )
             
                # Swift側で指定したキー名で取得
                history_json = form.getvalue("history") or "[]"
                audio_field = form["audio"]

                temp_file = FileUtil.temp_file()
                #送られてきた音声データ
                in_file = temp_file['in']
                # 読み上げ音声を保存するファイル
                out_file = temp_file['out']

                # 送られてきた音声バイナリを一時ファイルに保存
                with open(in_file, "wb") as f:
                    f.write(audio_field.file.read())

                # 非同期イベントループの作成と実行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response_json_str = loop.run_until_complete(
                    self.process_ai(in_file, out_file, history_json)
                )
                loop.close()

                # SwiftへJSONとして返却
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response_json_str.encode('utf-8'))

                # 一時ファイルの削除
                FileUtil.rm_f(in_file, out_file)
            
            except Exception as e:
                print(f"❌ Server Error: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_json = json.dumps({
                    "user_text": "Error",
                    "ai_text": f"Server Error: {str(e)}",
                    "audio_data": "",
                    "swift_action": "",
                    "parameters": {}
                })
                self.wfile.write(error_json.encode('utf-8'))
    
    """送られてきた音声を処理する"""
    def parse_voice_request(body, boundary):
        # boundaryを区切り文字として分割
        parts = body.split(b'--' + boundary)
        history = "{}"
        audio = None
        
        for part in parts:
            if b'name="history"' in part:
                # ヘッダーとボディの間の空行(\r\n\r\n)で分割して中身を取る
                history = part.split(b'\r\n\r\n')[1].strip(b'\r\n--').decode('utf-8')
            elif b'name="audio"' in part:
                audio = part.split(b'\r\n\r\n')[1].rstrip(b'\r\n--')
                
        return history, audio
 

    async def process_ai(self, in_file, out_file, history_json):
        """履歴を考慮した推論ロジック"""
        try:
            # 履歴のパース
            history = json.loads(history_json)

            # A. Whisperによる文字起こし
            with open(in_file, "rb") as f:
                user_text = groq_client.audio.transcriptions.create(
                    file=(in_file, f.read()),
                    model="whisper-large-v3-turbo",
                    language="ja"
                ).text
            # あいまい検索
            matched_intent = self.search_intent(user_text)

            # B.初期プロンプト組み立て
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_text})

            tools = []
            if matched_intent:
                properties = {}
                for p in matched_intent.get("parameters", []):
                    p_type = p.get("type", "string").lower()
                    if p_type not in ["string", "number", "integer", "boolean", "array", "object"]:
                        p_type = "string"
                    properties[p["name"]] = {
                        "type": p_type,
                        "description": p.get("description", "")
                    }
                
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": matched_intent.get("swift_action", "IntentAction"),
                            "description": matched_intent.get("summary", ""),
                            "parameters": {
                                "type": "object",
                                "properties": properties
                            }
                        }
                    }
                ]

            # C. Llamaによる回答生成
            chat_kwargs = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
            }
            if tools:
                chat_kwargs["tools"] = tools
                chat_kwargs["tool_choice"] = "auto"

            chat = groq_client.chat.completions.create(**chat_kwargs)
            message = chat.choices[0].message
            
            ai_text = message.content or ""
            swift_action = ""
            extracted_parameters = {}

            if message.tool_calls:
                tool_call = message.tool_calls[0]
                swift_action = tool_call.function.name
                try:
                    extracted_parameters = json.loads(tool_call.function.arguments)
                except:
                    print("エラーだよ〜〜〜")
                if not ai_text:
                    ai_text = "承知いたしました。操作を実行します。"

            # AIの回答も履歴に追加
            history.append({"role": "assistant", "content": ai_text})

            # D. Edge TTSによる音声合成
            await edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural").save(out_file)
            
            # E. 音声バイナリをBase64文字列に変換
            with open(out_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Swift側がデコードできるJSONを返す
            return json.dumps({
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_data": audio_b64,
                "swift_action": swift_action,
                "parameters": extracted_parameters
            })
        except Exception as e:
            return json.dumps({
                "user_text": "Error",
                "ai_text": f"AI Error: {str(e)}",
                "audio_data": "",
                "swift_action": "",
                "parameters": {}
            })

def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, VoiceAgentHandler)
    print(f"🚀 Server running on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()

    ```