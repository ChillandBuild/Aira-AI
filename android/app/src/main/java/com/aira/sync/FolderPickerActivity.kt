package com.aira.sync

import android.os.Bundle
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.io.File

class FolderPickerActivity : AppCompatActivity() {
    private lateinit var pathText: TextView
    private lateinit var listView: ListView
    private lateinit var currentDir: File

    private data class Entry(val label: String, val file: File?, val isUp: Boolean)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val startPath = intent.getStringExtra("start_path")
        currentDir = File(if (!startPath.isNullOrBlank()) startPath else "/storage/emulated/0")

        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL

        pathText = TextView(this)
        pathText.setPadding(24, 24, 24, 12)
        root.addView(pathText)

        listView = ListView(this)
        listView.layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f
        )
        root.addView(listView)

        val selectBtn = Button(this)
        selectBtn.text = "Select This Folder"
        selectBtn.setOnClickListener {
            val intent = android.content.Intent()
            intent.putExtra("folder_path", currentDir.absolutePath)
            setResult(RESULT_OK, intent)
            finish()
        }
        root.addView(selectBtn)

        setContentView(root)

        refreshList()

        listView.setOnItemClickListener { _, _, position, _ ->
            val entry = buildEntries()[position]
            if (entry.isUp) {
                currentDir.parentFile?.let { currentDir = it }
            } else {
                val target = entry.file ?: return@setOnItemClickListener
                currentDir = target
            }
            refreshList()
        }
    }

    private fun buildEntries(): List<Entry> {
        val entries = mutableListOf<Entry>()
        if (currentDir.parentFile != null) {
            entries.add(Entry(".. (Up)", null, true))
        }
        // listFiles() returns null for permission-denied/unreadable directories
        val subDirs = currentDir.listFiles { f -> f.isDirectory }
        subDirs?.sortedBy { it.name }?.forEach { dir ->
            entries.add(Entry(dir.name, dir, false))
        }
        return entries
    }

    private fun refreshList() {
        pathText.text = currentDir.absolutePath
        val labels = buildEntries().map { it.label }
        listView.adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, labels)
    }
}
