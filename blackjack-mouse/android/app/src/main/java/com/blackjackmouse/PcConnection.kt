package com.blackjackmouse

import android.os.Handler
import android.os.Looper
import java.io.IOException
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URLEncoder
import java.util.concurrent.Executors

/** Connexion TCP vers le serveur Python (voir server/blackjack_mouse_server.py). */
class PcConnection {
    private var socket: Socket? = null
    private var out: OutputStream? = null
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    @Volatile
    var onLost: (() -> Unit)? = null

    /** [onDone] reçoit null en cas de succès, sinon un message d'erreur. */
    fun connect(host: String, port: Int, pin: String, onDone: (String?) -> Unit) {
        Thread {
            close()
            val error: String? = try {
                val s = Socket()
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(host, port), 4000)
                s.soTimeout = 4000
                s.getOutputStream().apply {
                    write("AUTH $pin\n".toByteArray())
                    flush()
                }
                val reply = s.getInputStream().bufferedReader().readLine()
                if (reply == "OK") {
                    s.soTimeout = 0
                    socket = s
                    out = s.getOutputStream()
                    null
                } else {
                    s.close()
                    "PIN incorrect"
                }
            } catch (e: Exception) {
                "Connexion impossible (${e.message ?: e.javaClass.simpleName})"
            }
            main.post { onDone(error) }
        }.start()
    }

    private fun send(line: String) {
        io.execute {
            try {
                out?.apply {
                    write((line + "\n").toByteArray())
                    flush()
                }
            } catch (e: IOException) {
                close()
                main.post { onLost?.invoke() }
            }
        }
    }

    fun move(dx: Int, dy: Int) = send("MOVE $dx $dy")
    fun click(button: String) = send("CLICK $button")
    fun down(button: String = "left") = send("DOWN $button")
    fun up(button: String = "left") = send("UP $button")
    fun scroll(steps: Int) = send("SCROLL $steps")
    fun type(text: String) = send("TYPE " + URLEncoder.encode(text, "UTF-8"))
    fun key(combo: String) = send("KEY $combo")

    fun close() {
        try {
            socket?.close()
        } catch (_: IOException) {
        }
        socket = null
        out = null
    }
}
