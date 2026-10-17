import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls.Basic
import QtQuick.Effects

// Окно VoiceImitator в стиле Night Glass. Рисует видеокарта: фон, размытое стекло панелей
// и сам интерфейс; растягивание и перенос окна — системные (startSystemResize / Move),
// поэтому окно тянется так же плавно, как любое окно Windows.
Window {
    id: win
    width: 1152
    height: 826
    minimumWidth: 1060
    minimumHeight: 720
    color: Theme.window
    title: "VoiceImitator"
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinMaxButtonsHint

    // ---------- состояние (из настроек; каждое изменение уходит в backend.set) ----------
    property var info: backend.info()
    property var s: backend.settings()
    property bool ready: false
    property bool busy: false
    property string loadText: "Запуск…"
    property real loadProgress: -1
    property int tab: 0

    property string bgUrl: backend.background_url()
    property string bgMode: s.bg_mode
    property real bgBrightness: s.bg_brightness
    property real bgBlur: s.bg_blur
    property real glassBlur: s.glass_blur
    property var history: s.history
    property var outs: []
    property var ins: []
    property string cable: ""
    property string monitor: ""
    property string mic: ""
    property var cableInfo: ({ text: "", install: false, button: "Установить кабель", enabled: true })

    function set(key, value) { backend.set(key, value) }

    Component.onCompleted: {
        Theme.accent = s.accent
        Theme.frost = frost
        backend.start()
    }
    onClosing: {
        if (visibility !== Window.Maximized && visibility !== Window.Minimized)
            backend.saveWindow(width, height)
        backend.close()
    }

    Connections {
        target: backend
        function onLoading(text, progress) { win.loadText = text; win.loadProgress = progress }
        function onReady() { win.ready = true; backend.refreshDevices() }
        function onBusy(on) { win.busy = on }
        function onFlash(text) { footer.flash(text) }
        function onHistory(items) { win.history = items }
        function onBackground(url) { win.bgUrl = url; win.bgMode = backend.settings().bg_mode }
        function onDevices(d) {
            win.outs = d.outs; win.ins = d.ins
            win.cable = d.cable; win.monitor = d.monitor; win.mic = d.mic
        }
        function onCable(c) { win.cableInfo = c }
    }

    // ---------- фон ----------
    Item {
        id: scene
        anchors.fill: parent
        Image {
            id: photo
            anchors.fill: parent
            source: win.bgUrl
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 2560
            asynchronous: true
            visible: win.bgBlur <= 0
        }
        MultiEffect {   // размытие фона (0–20 px)
            anchors.fill: parent
            source: photo
            visible: win.bgBlur > 0
            blurEnabled: true
            blurMax: 32
            blur: win.bgBlur / 100 * 20 / 32
            autoPaddingEnabled: false
        }
        // яркость действует только на картинку: b% — чёрный с прозрачностью (100 − b)%
        Rectangle { anchors.fill: parent; color: "black"; opacity: win.bgMode === "sky" ? 0 : 1 - win.bgBrightness / 100 }
    }
    // стекло: тот же фон, размытый сильнее, — панели вырезают из него свой кусок
    MultiEffect {
        id: frost
        anchors.fill: scene
        source: scene
        visible: false
        layer.enabled: true
        blurEnabled: true
        blurMax: 64
        blur: Math.max(0.001, win.glassBlur / 100 * 40 / 64)
        autoPaddingEnabled: false
    }

    // ---------- рамка: заголовок, содержимое, строка версии ----------
    TitleBar {
        id: titleBar
        anchors.left: parent.left
        anchors.right: parent.right
        tabs: ["Озвучка", "Настройки", "Оформление"]
        current: win.tab
        showTabs: win.ready
        onSelect: (i) => win.tab = i
    }
    Footer {
        id: footer
        version: win.info.version
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: Theme.pad
        anchors.rightMargin: Theme.pad
        anchors.bottomMargin: 8
    }

    // содержимое не шире 1320 и на широком окне стоит по центру
    Item {
        id: content
        visible: win.ready
        width: Math.min(win.width - 2 * Theme.pad, Theme.maxWidth)
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: titleBar.bottom
        anchors.bottom: footer.top
        anchors.bottomMargin: Theme.gap - 8

        // ===== Озвучка =====
        Item {
            anchors.fill: parent
            visible: win.tab === 0
            // ширина делится строго 3:2 и не зависит от содержимого
            Section {
                id: speakPanel
                title: "Текст"
                width: (parent.width - Theme.gap) * 0.6
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 120
                    radius: Theme.rPill
                    color: Theme.fieldFill
                    border.width: 1
                    border.color: input.activeFocus ? Qt.rgba(1, 1, 1, 0.18) : Theme.fieldEdge
                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 1
                        TextArea {
                            id: input
                            wrapMode: TextArea.Wrap
                            color: Theme.text
                            selectionColor: Qt.rgba(1, 1, 1, 0.25)
                            font.family: Theme.font
                            font.pixelSize: 14
                            leftPadding: 10; rightPadding: 10; topPadding: 8; bottomPadding: 8
                            background: null
                            Keys.onPressed: (e) => {
                                if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) {
                                    backend.speak(input.text, false)
                                    e.accepted = true
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    spacing: 8
                    SolidButton {
                        Layout.fillWidth: true
                        implicitHeight: 42
                        text: win.busy ? "Озвучиваю…" : "Озвучить   Ctrl+Enter"
                        enabled: !win.busy
                        onClicked: backend.speak(input.text, false)
                    }
                    GhostButton { implicitWidth: 96; implicitHeight: 42; text: "Стоп"; onClicked: backend.stop() }
                }
                Text {
                    text: "История — нажмите, чтобы повторить"
                    color: Theme.faint
                    font.family: Theme.font
                    font.pixelSize: 12
                    Layout.topMargin: 12
                    Layout.bottomMargin: 6
                }
                HistoryList {
                    Layout.fillWidth: true
                    items: win.history
                    onPicked: (t) => backend.speak(t, true)
                }
            }
            Section {
                title: "Голос"
                bottomPad: 14
                x: speakPanel.width + Theme.gap
                width: (parent.width - Theme.gap) * 0.4
                Dropdown {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    model: win.info.presets
                    placeholder: "Пресеты…"
                    onPicked: (name) => {
                        var p = backend.preset(name)
                        voice.currentIndex = voice.find(p.voice)
                        speed.value = p.speed; pitch.value = p.pitch
                        win.set("voice", p.voice); win.set("speed", p.speed); win.set("pitch", p.pitch)
                    }
                }
                Dropdown {
                    id: voice
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    model: win.info.voices
                    Component.onCompleted: currentIndex = find(win.s.voice)
                    onPicked: (v) => win.set("voice", v)
                }
                SliderRow {
                    id: speed
                    title: "Скорость"; from: 0.5; to: 1.5; value: win.s.speed
                    format: (v) => v.toFixed(2) + "x"
                    onMoved: (v) => win.set("speed", Math.round(v * 1000) / 1000)
                }
                SliderRow {
                    id: pitch
                    title: "Тон"; from: -12; to: 12; value: win.s.pitch
                    format: (v) => (v >= 0.5 ? "+" : "") + v.toFixed(0) + " пт"
                    onMoved: (v) => win.set("pitch", Math.round(v * 10) / 10)
                }
                SliderRow {
                    title: "Громкость"; from: 0; to: 1; value: win.s.volume
                    format: (v) => Math.round(v * 100) + "%"
                    onMoved: (v) => win.set("volume", Math.round(v * 1000) / 1000)
                }
            }
        }

        // ===== Настройки (звук) =====
        RowLayout {
            anchors.left: parent.left
            anchors.right: parent.right
            visible: win.tab === 1
            spacing: Theme.gap
            ColumnLayout {
                Layout.preferredWidth: 1
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.gap
                Section {
                    title: "Микрофон для Discord"
                    Layout.fillWidth: true
                    Dropdown {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        model: win.outs
                        displayText: win.cable
                        onPicked: (v) => { win.cable = v; win.set("cable", v) }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.topMargin: 10
                        text: win.cableInfo.text
                        wrapMode: Text.WordWrap
                        color: Theme.muted
                        font.family: Theme.font
                        font.pixelSize: 12
                    }
                    SolidButton {
                        visible: win.cableInfo.install
                        Layout.topMargin: 12
                        implicitWidth: 190; implicitHeight: 34
                        text: win.cableInfo.button
                        enabled: win.cableInfo.enabled
                        onClicked: backend.installCable()
                    }
                    Text {
                        visible: win.cableInfo.install
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        text: win.info.credit
                        wrapMode: Text.WordWrap
                        color: Theme.faint
                        font.family: Theme.font
                        font.pixelSize: 11
                    }
                }
            }
            ColumnLayout {
                Layout.preferredWidth: 1
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: Theme.gap
                Section {
                    title: "Слышать озвучку в наушниках"
                    Layout.fillWidth: true
                    SwitchRow { checked: win.s.monitor_on; onToggled: (on) => win.set("monitor_on", on) }
                    Dropdown {
                        Layout.fillWidth: true
                        Layout.topMargin: 10
                        model: win.outs
                        displayText: win.monitor
                        onPicked: (v) => { win.monitor = v; win.set("monitor", v) }
                    }
                }
                Section {
                    title: "Пускать мой микрофон в кабель"
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 10
                        text: "Друзья услышат и озвучку, и ваш живой голос"
                        wrapMode: Text.WordWrap
                        color: Theme.muted
                        font.family: Theme.font
                        font.pixelSize: 12
                    }
                    SwitchRow { checked: win.s.mic_on; onToggled: (on) => win.set("mic_on", on) }
                    Dropdown {
                        Layout.fillWidth: true
                        Layout.topMargin: 10
                        model: win.ins
                        displayText: win.mic
                        onPicked: (v) => { win.mic = v; win.set("mic", v) }
                    }
                }
                GhostButton { implicitWidth: 180; text: "Обновить устройства"; onClicked: backend.rescan() }
            }
        }

        // ===== Оформление =====
        RowLayout {
            anchors.left: parent.left
            anchors.right: parent.right
            visible: win.tab === 2
            spacing: Theme.gap
            ColumnLayout {
                Layout.preferredWidth: 1
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                Section {
                    title: "Цвет-акцент"
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 12
                        text: "Красит то, что работает: вкладку, ползунки, переключатели"
                        wrapMode: Text.WordWrap
                        color: Theme.muted
                        font.family: Theme.font
                        font.pixelSize: 12
                    }
                    AccentPicker {
                        id: picker
                        Layout.fillWidth: true
                        swatches: win.info.accents
                        Component.onCompleted: {
                            var c = Qt.color(win.s.accent)
                            hue = win.s.accent_hue !== null && win.s.accent_hue !== undefined ? win.s.accent_hue
                                  : Math.max(0, c.hsvHue)
                            sat = c.hsvSaturation
                            val = c.hsvValue
                        }
                        onChanged: (c, h) => {
                            Theme.accent = c
                            win.set("accent", picker.hex(c).toLowerCase())
                            win.set("accent_hue", h)
                        }
                        onInvalid: (t) => footer.flash(t)
                    }
                }
            }
            ColumnLayout {
                Layout.preferredWidth: 1
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                Section {
                    title: "Фон и стекло"
                    Layout.fillWidth: true
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: [["picture", "Картинка"], ["custom", "Своя картинка…"], ["sky", "Звёздное небо"]]
                            delegate: GhostButton {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                implicitHeight: 32
                                text: modelData[1]
                                selected: win.bgMode === modelData[0]
                                dim: !selected
                                onClicked: {
                                    if (modelData[0] === "custom") backend.chooseBackground()
                                    else win.set("bg_mode", modelData[0])
                                }
                            }
                        }
                    }
                    Text {
                        Layout.topMargin: 6
                        Layout.bottomMargin: 2
                        text: win.bgMode === "sky" ? "Яркость действует только на картинку"
                              : win.bgMode === "custom" ? "Своя картинка" : "Грозовое небо над полем"
                        color: Theme.faint
                        font.family: Theme.font
                        font.pixelSize: 12
                    }
                    SliderRow {
                        id: bright
                        title: "Яркость фона"; from: 0; to: 100; stepSize: 1; value: win.bgBrightness
                        enabled: win.bgMode !== "sky"
                        format: (v) => Math.round(v) + "%"
                        onMoved: (v) => { win.bgBrightness = v; win.set("bg_brightness", Math.round(v)) }
                    }
                    SliderRow {
                        id: bgBlurRow
                        title: "Размытие фона"; from: 0; to: 100; stepSize: 1; value: win.bgBlur
                        format: (v) => Math.round(v) + "%"
                        onMoved: (v) => { win.bgBlur = v; win.set("bg_blur", Math.round(v)) }
                    }
                    SliderRow {
                        id: glassRow
                        title: "Размытие стекла"; from: 0; to: 100; stepSize: 1; value: win.glassBlur
                        format: (v) => Math.round(v) + "%"
                        onMoved: (v) => { win.glassBlur = v; win.set("glass_blur", Math.round(v)) }
                    }
                    GhostButton {
                        Layout.topMargin: 16
                        implicitHeight: 32
                        text: "Сбросить"
                        onClicked: {
                            win.bgBrightness = 50; win.bgBlur = 0; win.glassBlur = 60
                            bright.value = 50; bgBlurRow.value = 0; glassRow.value = 60
                            win.set("bg_brightness", 50); win.set("bg_blur", 0); win.set("glass_blur", 60)
                            win.set("bg_mode", "picture")
                        }
                    }
                }
            }
        }
    }

    // ---------- экран загрузки ----------
    Glass {
        visible: !win.ready
        anchors.centerIn: parent
        width: 472
        height: 190
        Column {
            anchors.centerIn: parent
            spacing: 14
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "VoiceImitator"
                color: Theme.text
                font.family: Theme.font
                font.pixelSize: 28
                font.bold: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 400
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: win.loadText
                color: Theme.muted
                font.family: Theme.font
                font.pixelSize: 13
            }
            Rectangle {   // шкала: с долей — заполняется, без — бегущий отрезок
                anchors.horizontalCenter: parent.horizontalCenter
                width: 360; height: 4; radius: 2
                color: Theme.trackOff
                clip: true
                Rectangle {
                    height: parent.height; radius: 2
                    color: Theme.accent
                    width: win.loadProgress >= 0 ? parent.width * win.loadProgress : parent.width * 0.3
                    x: win.loadProgress >= 0 ? 0 : runner.pos * (parent.width * 1.3) - parent.width * 0.3
                }
                QtObject { id: runner; property real pos: 0 }
                NumberAnimation {
                    target: runner; property: "pos"; from: 0; to: 1; duration: 1300
                    loops: Animation.Infinite; running: win.loadProgress < 0 && !win.ready
                    easing.type: Easing.InOutQuad
                }
            }
        }
    }

    // ---------- края окна: системное растягивание (как ResizeBorderThickness=6) ----------
    component Edge: MouseArea {
        property int edges
        enabled: win.visibility !== Window.Maximized
        onPressed: win.startSystemResize(edges)
    }
    readonly property int rb: 6
    Edge { edges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor; y: rb; width: rb; height: win.height - 2 * rb }
    Edge { edges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor; x: win.width - rb; y: rb; width: rb; height: win.height - 2 * rb }
    Edge { edges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor; x: rb; width: win.width - 2 * rb; height: rb }
    Edge { edges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor; x: rb; y: win.height - rb; width: win.width - 2 * rb; height: rb }
    Edge { edges: Qt.TopEdge | Qt.LeftEdge; cursorShape: Qt.SizeFDiagCursor; width: rb * 2; height: rb * 2 }
    Edge { edges: Qt.BottomEdge | Qt.RightEdge; cursorShape: Qt.SizeFDiagCursor; x: win.width - rb * 2; y: win.height - rb * 2; width: rb * 2; height: rb * 2 }
    Edge { edges: Qt.TopEdge | Qt.RightEdge; cursorShape: Qt.SizeBDiagCursor; x: win.width - rb * 2; width: rb * 2; height: rb * 2 }
    Edge { edges: Qt.BottomEdge | Qt.LeftEdge; cursorShape: Qt.SizeBDiagCursor; y: win.height - rb * 2; width: rb * 2; height: rb * 2 }
}
