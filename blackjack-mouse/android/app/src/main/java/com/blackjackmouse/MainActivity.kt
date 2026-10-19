package com.blackjackmouse

import android.content.SharedPreferences
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.max

// Palette « table de Blackjack »
private val FeltLight = Color(0xFF0B5D2E)
private val FeltDark = Color(0xFF063D1E)
private val Gold = Color(0xFFD4AF37)
private val Ivory = Color(0xFFF8F4E3)
private val CardRed = Color(0xFFB3202A)
private val CardBlack = Color(0xFF14110F)

class MainActivity : ComponentActivity() {
    private val pc = PcConnection()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val prefs = getSharedPreferences("blackjack_mouse", MODE_PRIVATE)
        setContent { App(pc, prefs) }
    }

    override fun onDestroy() {
        pc.close()
        super.onDestroy()
    }
}

@Composable
private fun App(pc: PcConnection, prefs: SharedPreferences) {
    var connected by remember { mutableStateOf(false) }
    DisposableEffect(Unit) {
        pc.onLost = { connected = false }
        onDispose { pc.onLost = null }
    }
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(FeltLight, FeltDark)))
            .systemBarsPadding()
            .imePadding()
    ) {
        if (connected) {
            ControlScreen(pc) {
                pc.close()
                connected = false
            }
        } else {
            ConnectScreen(pc, prefs) { connected = true }
        }
    }
}

@Composable
private fun Title(size: Int = 32) {
    Text(
        "♠ Blackjack Mouse ♥",
        color = Gold,
        fontSize = size.sp,
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Bold,
        textAlign = TextAlign.Center,
    )
}

@Composable
private fun ConnectScreen(pc: PcConnection, prefs: SharedPreferences, onConnected: () -> Unit) {
    var ip by remember { mutableStateOf(prefs.getString("ip", "") ?: "") }
    var port by remember { mutableStateOf(prefs.getString("port", "5555") ?: "5555") }
    var pin by remember { mutableStateOf(prefs.getString("pin", "") ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }

    val fieldColors = OutlinedTextFieldDefaults.colors(
        focusedTextColor = Ivory,
        unfocusedTextColor = Ivory,
        focusedBorderColor = Gold,
        unfocusedBorderColor = Gold.copy(alpha = 0.5f),
        focusedLabelColor = Gold,
        unfocusedLabelColor = Ivory.copy(alpha = 0.7f),
        cursorColor = Gold,
    )

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Title(34)
        Text("♦  ♣  ♦  ♣", color = Gold.copy(alpha = 0.7f), fontSize = 18.sp)
        Text(
            "Lance blackjack_mouse_server.py sur ton PC,\npuis entre l'IP et le PIN affichés.",
            color = Ivory.copy(alpha = 0.85f),
            textAlign = TextAlign.Center,
        )
        OutlinedTextField(
            value = ip, onValueChange = { ip = it.trim() },
            label = { Text("IP du PC (ex : 192.168.1.20)") },
            singleLine = true, colors = fieldColors, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(
                value = port, onValueChange = { port = it.filter(Char::isDigit) },
                label = { Text("Port") }, singleLine = true, colors = fieldColors,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
            OutlinedTextField(
                value = pin, onValueChange = { pin = it.trim() },
                label = { Text("PIN") }, singleLine = true, colors = fieldColors,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
        }
        error?.let { Text(it, color = Color(0xFFFF8A80), textAlign = TextAlign.Center) }
        Button(
            enabled = !loading && ip.isNotEmpty() && port.isNotEmpty(),
            onClick = {
                loading = true
                error = null
                prefs.edit().putString("ip", ip).putString("port", port).putString("pin", pin).apply()
                pc.connect(ip, port.toIntOrNull() ?: 5555, pin) { err ->
                    loading = false
                    if (err == null) onConnected() else error = err
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Gold, contentColor = CardBlack),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            Text(if (loading) "Distribution…" else "Jouer ♠", fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun ControlScreen(pc: PcConnection, onLeave: () -> Unit) {
    var tab by remember { mutableStateOf(0) }
    Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { Title(22) }
            Text(
                "Quitter",
                color = Ivory,
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .border(BorderStroke(1.dp, Gold.copy(alpha = 0.6f)), RoundedCornerShape(8.dp))
                    .clickable(onClick = onLeave)
                    .padding(horizontal = 12.dp, vertical = 6.dp),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            TabButton("♠ Souris", tab == 0, Modifier.weight(1f)) { tab = 0 }
            TabButton("♥ Clavier", tab == 1, Modifier.weight(1f)) { tab = 1 }
        }
        Box(Modifier.weight(1f)) {
            if (tab == 0) MouseTab(pc) else KeyboardTab(pc)
        }
    }
}

@Composable
private fun TabButton(label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Box(
        modifier
            .height(44.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(if (selected) Gold else Color.Black.copy(alpha = 0.25f))
            .border(BorderStroke(1.dp, Gold), RoundedCornerShape(10.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (selected) CardBlack else Gold,
            fontWeight = FontWeight.Bold,
            fontSize = 16.sp,
        )
    }
}

@Composable
private fun PlayingCard(rank: String, suit: String, label: String, red: Boolean, highlighted: Boolean = false, onClick: () -> Unit) {
    val ink = if (red) CardRed else CardBlack
    Column(
        Modifier
            .width(84.dp)
            .height(104.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(Ivory)
            .border(BorderStroke(if (highlighted) 3.dp else 1.dp, if (highlighted) Gold else Color.Gray), RoundedCornerShape(10.dp))
            .clickable(onClick = onClick)
            .padding(6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Text("$rank$suit", color = ink, fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.align(Alignment.Start))
        Text(suit, color = ink, fontSize = 30.sp)
        Text(label, color = ink, fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun MouseTab(pc: PcConnection) {
    var sensitivity by remember { mutableFloatStateOf(1.8f) }
    var dragging by remember { mutableStateOf(false) }
    val sens by rememberUpdatedState(sensitivity)

    DisposableEffect(Unit) {
        onDispose { pc.up() } // ne jamais laisser le bouton bloqué sur le PC
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxSize()) {
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Brush.radialGradient(listOf(FeltLight, FeltDark)))
                .border(BorderStroke(3.dp, Gold), RoundedCornerShape(18.dp))
                .pointerInput(Unit) {
                    var remX = 0f
                    var remY = 0f
                    var remScroll = 0f
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        val startTime = down.uptimeMillis
                        var endTime = startTime
                        var maxPointers = 1
                        var travel = 0f
                        do {
                            val event = awaitPointerEvent()
                            val pressed = event.changes.filter { it.pressed }
                            endTime = event.changes.maxOf { it.uptimeMillis }
                            maxPointers = max(maxPointers, pressed.size)
                            if (pressed.isNotEmpty()) {
                                var delta = Offset.Zero
                                pressed.forEach { delta += it.position - it.previousPosition }
                                delta /= pressed.size.toFloat()
                                travel += abs(delta.x) + abs(delta.y)
                                if (pressed.size >= 2) {
                                    remScroll += delta.y
                                    val steps = (remScroll / 18f).toInt()
                                    if (steps != 0) {
                                        remScroll -= steps * 18f
                                        pc.scroll(steps)
                                    }
                                } else if (maxPointers == 1) {
                                    remX += delta.x * sens
                                    remY += delta.y * sens
                                    val ix = remX.toInt()
                                    val iy = remY.toInt()
                                    remX -= ix
                                    remY -= iy
                                    if (ix != 0 || iy != 0) pc.move(ix, iy)
                                }
                                pressed.forEach { it.consume() }
                            }
                        } while (event.changes.any { it.pressed })
                        // Petit tap rapide = clic (1 doigt : gauche, 2 doigts : droit)
                        if (travel < 20f && endTime - startTime < 300) {
                            pc.click(if (maxPointers >= 2) "right" else "left")
                        }
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "♠ ♥ ♦ ♣\n\nGlisse : déplacer\nTap : clic gauche\nTap 2 doigts : clic droit\nGlisse 2 doigts : défiler",
                color = Gold.copy(alpha = 0.35f),
                textAlign = TextAlign.Center,
                fontSize = 15.sp,
                fontFamily = FontFamily.Serif,
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            PlayingCard("A", "♠", "Clic gauche", red = false) { pc.click("left") }
            PlayingCard("J", "♦", if (dragging) "Lâcher" else "Glisser", red = true, highlighted = dragging) {
                dragging = !dragging
                if (dragging) pc.down() else pc.up()
            }
            PlayingCard("K", "♥", "Clic droit", red = true) { pc.click("right") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Vitesse", color = Ivory, fontSize = 14.sp)
            Slider(
                value = sensitivity,
                onValueChange = { sensitivity = it },
                valueRange = 0.8f..4f,
                colors = SliderDefaults.colors(thumbColor = Gold, activeTrackColor = Gold),
                modifier = Modifier.padding(start = 12.dp),
            )
        }
    }
}

@Composable
private fun KeyboardTab(pc: PcConnection) {
    var text by remember { mutableStateOf("") }
    val scroll = rememberScrollState()

    Column(
        Modifier.fillMaxSize().verticalScroll(scroll),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Tape ici : chaque caractère part directement sur le PC.", color = Ivory.copy(alpha = 0.85f), fontSize = 14.sp)
        OutlinedTextField(
            value = text,
            onValueChange = { new ->
                // Envoie seulement la différence : suppressions puis ajouts
                var prefix = 0
                val limit = minOf(text.length, new.length)
                while (prefix < limit && text[prefix] == new[prefix]) prefix++
                repeat(text.length - prefix) { pc.key("backspace") }
                if (new.length > prefix) pc.type(new.substring(prefix))
                text = new
            },
            placeholder = { Text("Clavier du PC…", color = Ivory.copy(alpha = 0.4f)) },
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = Ivory,
                unfocusedTextColor = Ivory,
                focusedBorderColor = Gold,
                unfocusedBorderColor = Gold.copy(alpha = 0.5f),
                cursorColor = Gold,
            ),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.VisiblePassword, // pas de correcteur : caractère par caractère
                imeAction = ImeAction.Send,
            ),
            keyboardActions = KeyboardActions(onSend = {
                pc.key("enter")
                text = ""
            }),
            modifier = Modifier.fillMaxWidth(),
        )

        Text("Touches spéciales", color = Gold, fontWeight = FontWeight.Bold)
        KeyRow(pc, "Entrée" to "enter", "⌫" to "backspace", "Suppr" to "delete", "Échap" to "esc")
        KeyRow(pc, "Tab" to "tab", "Espace" to "space", "Win" to "cmd", "Alt+Tab" to "alt+tab")
        KeyRow(pc, "←" to "left", "↑" to "up", "↓" to "down", "→" to "right")
        KeyRow(pc, "Début" to "home", "Fin" to "end", "Pg ▲" to "page_up", "Pg ▼" to "page_down")
        Text("Raccourcis", color = Gold, fontWeight = FontWeight.Bold)
        KeyRow(pc, "Copier" to "ctrl+c", "Coller" to "ctrl+v", "Couper" to "ctrl+x", "Tout" to "ctrl+a")
        KeyRow(pc, "Annuler" to "ctrl+z", "Fermer" to "alt+f4", "F5" to "f5", "Plein écran" to "f11")
    }
}

@Composable
private fun KeyRow(pc: PcConnection, vararg keys: Pair<String, String>) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        keys.forEach { (label, combo) ->
            Box(
                Modifier
                    .weight(1f)
                    .height(46.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(Ivory)
                    .clickable { pc.key(combo) },
                contentAlignment = Alignment.Center,
            ) {
                Text(label, color = CardBlack, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, textAlign = TextAlign.Center)
            }
        }
    }
}
