import QtQuick
import QtQuick.Layouts

// Стеклянная панель с заголовком; содержимое — столбиком, поля 20 по бокам и снизу.
Glass {
    id: sec
    property string title
    property int bottomPad: 20
    default property alias content: col.data
    implicitHeight: col.implicitHeight + 18 + bottomPad

    ColumnLayout {
        id: col
        x: 20
        y: 18
        width: sec.width - 40
        spacing: 0
        Text {
            text: sec.title
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: 14
            font.bold: true
            Layout.bottomMargin: 8
        }
    }
}
