pub const PRODUCT_NAME: &str = "Research Observatory";

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("Research Observatory desktop runtime failed");
}

#[cfg(test)]
mod tests {
    use super::PRODUCT_NAME;

    #[test]
    fn product_identity_is_stable() {
        assert_eq!(PRODUCT_NAME, "Research Observatory");
    }
}
