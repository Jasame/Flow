// no console window behind 语流 on Windows (release builds)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    flow_desktop_lib::run()
}
