use std::env;

#[derive(Debug)]
struct HardwareInput {
    uptime_seconds: f64,
    load_one: f64,
    memory_total_kb: u64,
    memory_available_kb: u64,
    swap_total_kb: u64,
    swap_free_kb: u64,
    thermal_zones: u64,
    max_celsius: f64,
    cpu_pressure_avg10: f64,
    memory_pressure_avg10: f64,
    io_pressure_avg10: f64,
    root_total_bytes: u64,
    root_available_bytes: u64,
    block_devices: u64,
}

fn parse_f64(value: &str, name: &str) -> Result<f64, String> {
    let parsed = value.parse::<f64>().map_err(|_| format!("{name}: invalid number"))?;
    if !parsed.is_finite() {
        return Err(format!("{name}: non-finite number"));
    }
    Ok(parsed)
}

fn parse_u64(value: &str, name: &str) -> Result<u64, String> {
    value.parse::<u64>().map_err(|_| format!("{name}: invalid integer"))
}

fn parse_input(args: &[String]) -> Result<HardwareInput, String> {
    if args.len() != 14 {
        return Err(format!("expected 14 telemetry arguments, got {}", args.len()));
    }
    Ok(HardwareInput {
        uptime_seconds: parse_f64(&args[0], "uptime_seconds")?,
        load_one: parse_f64(&args[1], "load_one")?,
        memory_total_kb: parse_u64(&args[2], "memory_total_kb")?,
        memory_available_kb: parse_u64(&args[3], "memory_available_kb")?,
        swap_total_kb: parse_u64(&args[4], "swap_total_kb")?,
        swap_free_kb: parse_u64(&args[5], "swap_free_kb")?,
        thermal_zones: parse_u64(&args[6], "thermal_zones")?,
        max_celsius: parse_f64(&args[7], "max_celsius")?,
        cpu_pressure_avg10: parse_f64(&args[8], "cpu_pressure_avg10")?,
        memory_pressure_avg10: parse_f64(&args[9], "memory_pressure_avg10")?,
        io_pressure_avg10: parse_f64(&args[10], "io_pressure_avg10")?,
        root_total_bytes: parse_u64(&args[11], "root_total_bytes")?,
        root_available_bytes: parse_u64(&args[12], "root_available_bytes")?,
        block_devices: parse_u64(&args[13], "block_devices")?,
    })
}

fn validate(input: &HardwareInput) -> Result<(), String> {
    if input.uptime_seconds < -1.0 {
        return Err("uptime_seconds below sentinel minimum".into());
    }
    if input.load_one < 0.0 || input.load_one > 1_000_000.0 {
        return Err("load_one outside safe range".into());
    }
    if input.memory_total_kb == 0 {
        return Err("memory_total_kb must be positive".into());
    }
    if input.memory_available_kb > input.memory_total_kb {
        return Err("memory_available_kb exceeds memory_total_kb".into());
    }
    if input.swap_free_kb > input.swap_total_kb {
        return Err("swap_free_kb exceeds swap_total_kb".into());
    }
    if input.thermal_zones > 4096 {
        return Err("thermal_zones exceeds safety limit".into());
    }
    if input.thermal_zones > 0 && !(input.max_celsius >= -100.0 && input.max_celsius <= 250.0) {
        return Err("max_celsius outside physical safety range".into());
    }
    for (name, value) in [
        ("cpu_pressure_avg10", input.cpu_pressure_avg10),
        ("memory_pressure_avg10", input.memory_pressure_avg10),
        ("io_pressure_avg10", input.io_pressure_avg10),
    ] {
        if value != -1.0 && !(0.0..=100.0).contains(&value) {
            return Err(format!("{name} outside PSI range"));
        }
    }
    if input.root_total_bytes > 0 && input.root_available_bytes > input.root_total_bytes {
        return Err("root_available_bytes exceeds root_total_bytes".into());
    }
    if input.block_devices > 4096 {
        return Err("block_devices exceeds safety limit".into());
    }
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    match parse_input(&args).and_then(|input| validate(&input)) {
        Ok(()) => {
            println!("ok");
        }
        Err(error) => {
            eprintln!("ithute-hardware-validator: {error}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid() -> HardwareInput {
        HardwareInput {
            uptime_seconds: 1000.0,
            load_one: 1.5,
            memory_total_kb: 16_000_000,
            memory_available_kb: 8_000_000,
            swap_total_kb: 2_000_000,
            swap_free_kb: 1_900_000,
            thermal_zones: 2,
            max_celsius: 48.0,
            cpu_pressure_avg10: 0.5,
            memory_pressure_avg10: 0.0,
            io_pressure_avg10: -1.0,
            root_total_bytes: 100_000_000,
            root_available_bytes: 40_000_000,
            block_devices: 2,
        }
    }

    #[test]
    fn accepts_sane_sample() {
        assert!(validate(&valid()).is_ok());
    }

    #[test]
    fn rejects_available_memory_above_total() {
        let mut input = valid();
        input.memory_available_kb = input.memory_total_kb + 1;
        assert!(validate(&input).is_err());
    }

    #[test]
    fn rejects_impossible_temperature() {
        let mut input = valid();
        input.max_celsius = 900.0;
        assert!(validate(&input).is_err());
    }

    #[test]
    fn rejects_invalid_pressure() {
        let mut input = valid();
        input.io_pressure_avg10 = 101.0;
        assert!(validate(&input).is_err());
    }
}
