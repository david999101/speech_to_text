from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from vosk import Model, KaldiRecognizer
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", transports=['websocket'])

model = Model("model")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ka">
<head>
    <meta charset="UTF-8">
    <title>ქართული Live STT (WebSockets)</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            text-align: center; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            padding: 40px; 
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            box-sizing: border-box;
        }
        .box { 
            max-width: 600px; 
            width: 100%;
            background: white; 
            padding: 40px; 
            border-radius: 16px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.15); 
        }
        h2 { color: #333; margin-bottom: 30px; font-weight: 600; }
        
        .btn-container {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 140px;
            margin-bottom: 20px;
        }

        .mic-btn { 
            width: 90px; 
            height: 90px; 
            font-size: 32px; 
            background: #4CAF50; 
            color: white; 
            border: none; 
            border-radius: 50%; 
            cursor: pointer; 
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
            outline: none;
        }
        .mic-btn:hover {
            transform: scale(1.05);
        }

        .mic-btn.recording { 
            background: #f44336; 
            box-shadow: 0 6px 20px rgba(244, 67, 54, 0.4);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7); }
            70% { box-shadow: 0 0 0 20px rgba(244, 67, 54, 0); }
            100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0); }
        }

        #text { 
            margin-top: 30px; 
            font-size: 20px; 
            line-height: 1.6;
            color: #2c3e50;
            min-height: 80px; 
            text-align: left; 
            background: #f8f9fa; 
            padding: 20px; 
            border-radius: 8px;
            border-left: 5px solid #4CAF50; 
            white-space: pre-wrap; 
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.02);
        }
        
        .status-hint {
            font-size: 14px;
            color: #777;
            margin-top: 10px;
        }
    </style>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head>
<body>
    <div class="box">
        <h2>🎙️ ქართული ხმის Live ამოცნობა</h2>
        
        <div class="btn-container">
            <button id="btn" class="mic-btn">🎤</button>
        </div>
        <div id="status" class="status-hint">დააჭირეთ მიკროფონს საუბრის დასაწყებად</div>

        <div id="text">აქ გამოჩნდება ტექსტი...</div>
    </div>

    <script>
        let btn = document.getElementById('btn');
        let textDiv = document.getElementById('text');
        let statusDiv = document.getElementById('status');
        let socket = io({ transports: ['websocket'] });
        let audioContext;
        let processor;
        let input;
        let globalStream;
        let isRecording = false;

        socket.on('speech_result', (data) => {
            if (data.text) {
                textDiv.innerHTML = data.text;
            }
        });

        btn.onclick = async () => {
            if (isRecording) {
                isRecording = false;
                btn.classList.remove('recording');
                statusDiv.textContent = "ჩაწერა შეჩერდა. ჩასართავად კვლავ დააჭირეთ მიკროფონს.";
                
                // უსაფრთხო გათიშვა, რომ ბოლო ფრაგმენტები არ გაიპაროს სერვერზე
                if (processor) { processor.onaudioprocess = null; processor.disconnect(); }
                if (input) input.disconnect();
                if (globalStream) globalStream.getTracks().forEach(track => track.stop());
                if (audioContext) audioContext.close();
                
                socket.emit('stop_stream');
                return;
            }

            try {
                globalStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                input = audioContext.createMediaStreamSource(globalStream);
                // 2048 ზომის ბლოკი უფრო სტაბილურია და სწრაფად აწვდის Vosk-ს ინფორმაციას
                processor = audioContext.createScriptProcessor(2048, 1, 1);
                
                input.connect(processor);
                processor.connect(audioContext.destination);

                isRecording = true;
                btn.classList.add('recording');
                statusDiv.textContent = "სისტემა გისმენთ... ილაპარაკეთ";
                textDiv.innerHTML = "<i>მიმდინარეობს საუბრის გარდაქმნა...</i>";
                
                socket.emit('start_stream');

                processor.onaudioprocess = (e) => {
                    if (!isRecording) return;
                    let left = e.inputBuffer.getChannelData(0);
                    let l = left.length;
                    let buf = new Int16Array(l);
                    let hasSignal = false;
                    while (l--) {
                        buf[l] = Math.min(1, left[l]) * 0x7FFF;
                        if (buf[l] !== 0) hasSignal = true;
                    }
                    // ვგზავნით მხოლოდ იმ შემთხვევაში, თუ ბუფერი სრულიად ცარიელი (ნულოვანი) არაა
                    if (hasSignal) {
                        socket.emit('audio_data', buf.buffer);
                    }
                };
            } catch (err) {
                alert("მიკროფონთან წვდომა უარყოფილია ან მოწყობილობა ვერ მოიძებნა.");
            }
        };
    </script>
</body>
</html>
"""

user_recognizers = {}
user_texts = {}

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('start_stream')
def handle_start():
    from flask import request
    user_recognizers[request.sid] = KaldiRecognizer(model, 16000)
    user_texts[request.sid] = ""

@socketio.on('audio_data')
def handle_audio(data):
    from flask import request
    sid = request.sid
    if sid not in user_recognizers:
        return
        
    rec = user_recognizers[sid]
    
    # თუ მონაცემები ძალიან მცირეა, გამოვტოვოთ Vosk-ის დასაცავად
    if len(data) < 32:
        return

    try:
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            text = res.get("text", "")
            if text:
                user_texts[sid] += text + " "
                emit('speech_result', {'text': user_texts[sid]})
        else:
            res = json.loads(rec.PartialResult())
            p_text = res.get("partial", "")
            if p_text:
                current_full_text = user_texts[sid] + f" <span style='color: #7f8c8d; font-style: italic;'>{p_text}...</span>"
                emit('speech_result', {'text': current_full_text})
    except Exception:
        pass

@socketio.on('stop_stream')
def handle_stop():
    from flask import request
    sid = request.sid
    if sid in user_recognizers:
        rec = user_recognizers[sid]
        try:
            res = json.loads(rec.FinalResult())
            text = res.get("text", "")
            if text:
                user_texts[sid] += text
            emit('speech_result', {'text': f"<strong>{user_texts[sid]}</strong>"})
        except Exception:
            pass
        finally:
            if sid in user_recognizers: del user_recognizers[sid]
            if sid in user_texts: del user_texts[sid]