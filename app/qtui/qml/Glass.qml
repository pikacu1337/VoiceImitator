import QtQuick
import QtQuick.Effects

// Панель из матового стекла: кусок размытого фона под ней, затемнение, вуаль и обводка 1px.
// Всё считает видеокарта, поэтому при растягивании окна стекло едет вместе с панелью.
Item {
    id: g
    property real radius: Theme.rCard

    // место панели в окне — пересчитывается, когда сдвигается она сама или любой из родителей
    property rect area: {
        for (var p = g; p; p = p.parent) { p.x; p.y; p.width; p.height }
        var pt = g.mapToItem(null, 0, 0)
        return Qt.rect(pt.x, pt.y, g.width, g.height)
    }

    ShaderEffectSource {
        id: piece
        anchors.fill: parent
        sourceItem: Theme.frost
        sourceRect: g.area
        visible: false
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: g.radius
        visible: false
        layer.enabled: true
        antialiasing: true
    }
    MultiEffect {
        anchors.fill: parent
        source: piece
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }
    Rectangle { anchors.fill: parent; radius: g.radius; color: Qt.rgba(0, 0, 0, Theme.glassDim) }
    Rectangle {
        anchors.fill: parent
        radius: g.radius
        color: Qt.rgba(1, 1, 1, Theme.veil)
        border.color: Theme.edge
        border.width: 1
    }
}
