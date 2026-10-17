import QtQuick
import QtQuick.Layouts

// Строка, как в настройках ZapretLauncher: название слева, справа ползунок постоянной
// ширины 170 и значение по правому краю — при растягивании окна ползунок не растёт.
RowLayout {
    id: row
    property string title
    property alias from: slider.from
    property alias to: slider.to
    property alias value: slider.value
    property alias stepSize: slider.stepSize
    property var format: (v) => v.toFixed(2)
    signal moved(real value)
    spacing: 0
    Layout.fillWidth: true
    Layout.topMargin: 10

    Text {
        text: row.title
        color: Theme.text
        font.family: Theme.font
        font.pixelSize: 14
        Layout.fillWidth: true
        opacity: row.enabled ? 1 : 0.4
    }
    NgSlider {
        id: slider
        Layout.leftMargin: 12
        Layout.rightMargin: 8
        onMoved: (v) => row.moved(v)
    }
    Text {
        text: row.format(slider.value)
        color: Theme.muted
        font.family: Theme.font
        font.pointSize: 12.5 * 0.75
        horizontalAlignment: Text.AlignRight
        Layout.preferredWidth: 48
        opacity: row.enabled ? 1 : 0.4
    }
}
