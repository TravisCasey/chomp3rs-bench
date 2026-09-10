//! Run the chomp3rs cubical homology pipeline on one case file and print a
//! single JSON record describing the run.
//!
//! ```text
//! chomp3rs-driver <case.csv> --columns plain|graded|extent|graded_extent
//!     [--backend sequential|rayon] [--threads N]
//!     [--max-critical-dimension K] [--modulus P]
//! ```

use std::{
    fs,
    path::{Path, PathBuf},
    process::exit,
    time::Instant,
};

use chomp3rs::{
    io::{read_graded_orthants_csv, read_orthants_csv},
    prelude::*,
};
use clap::{Parser, ValueEnum};
use serde::Serialize;

const CHOMP3RS_REV: &str = "2f15ddbcf96f9df2650000bf8265c28e782ce57a";

#[derive(Parser)]
#[command(about = "Run the chomp3rs pipeline on a cubical case file and print one JSON record")]
struct Arguments {
    /// Case file holding the maximal cubes, one per line.
    case_path: PathBuf,
    /// Column layout of the case file.
    #[arg(long, value_enum)]
    columns: Columns,
    /// Execution backend the library dispatches on.
    #[arg(long, value_enum, default_value_t = Backend::Sequential)]
    backend: Backend,
    /// Rayon thread count; the sequential backend runs on one thread whatever
    /// this says.
    #[arg(long, default_value_t = 1)]
    threads: usize,
    /// Cap on the dimension of the critical cells the matching reports.
    #[arg(long)]
    max_critical_dimension: Option<u32>,
    /// Prime modulus of the coefficient field.
    #[arg(long, default_value_t = 2)]
    modulus: u32,
}

#[derive(Clone, Copy, ValueEnum)]
enum Columns {
    Plain,
    Graded,
    Extent,
    #[value(name = "graded_extent")]
    GradedExtent,
}

impl Columns {
    fn name(self) -> &'static str {
        match self {
            Self::Plain => "plain",
            Self::Graded => "graded",
            Self::Extent => "extent",
            Self::GradedExtent => "graded_extent",
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum Backend {
    Sequential,
    Rayon,
}

impl Backend {
    fn name(self) -> &'static str {
        match self {
            Self::Sequential => "sequential",
            Self::Rayon => "rayon",
        }
    }
}

/// The maximal cubes of a case file, in the shape its layout gives them.
enum CaseCubes {
    Orthants(Vec<Orthant>),
    GradedOrthants(Vec<(Orthant, u32)>),
    Cubes(Vec<(Cube, u32)>),
}

impl CaseCubes {
    fn len(&self) -> usize {
        match self {
            Self::Orthants(orthants) => orthants.len(),
            Self::GradedOrthants(orthants) => orthants.len(),
            Self::Cubes(cubes) => cubes.len(),
        }
    }
}

#[derive(Serialize)]
struct Record {
    tool: &'static str,
    tool_version: &'static str,
    config: Config,
    stages: Vec<Stage>,
    answer: Answer,
}

#[derive(Serialize)]
struct Config {
    backend: &'static str,
    threads: usize,
    columns: &'static str,
    max_critical_dimension: Option<u32>,
    modulus: u32,
}

#[derive(Serialize)]
struct Stage {
    name: &'static str,
    seconds: f64,
    cells_in: usize,
    cells_out: usize,
}

#[derive(Serialize)]
struct Answer {
    betti: Vec<u32>,
    bar_counts: Vec<u32>,
    bars_finite: Vec<u32>,
    bars_essential: Vec<u32>,
}

fn stage(name: &'static str, seconds: f64, cells_in: usize, cells_out: usize) -> Stage {
    Stage {
        name,
        seconds,
        cells_in,
        cells_out,
    }
}

fn fail(message: &str) -> ! {
    eprintln!("{message}");
    exit(1);
}

/// Read a case file whose last column is an extent string, one character per
/// axis, and whose second-to-last column is the grade when `graded`.
fn read_extent_csv(path: &Path, graded: bool) -> Result<Vec<(Cube, u32)>, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("could not read {}: {error}", path.display()))?;
    let mut cubes = Vec::new();

    for (index, line) in text.lines().enumerate() {
        let line_number = index + 1;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let fields: Vec<&str> = trimmed.split(',').map(str::trim).collect();
        let extent_text = fields[fields.len() - 1];
        let coordinate_count = if graded {
            fields.len() - 2
        } else {
            fields.len() - 1
        };
        let grade = if graded {
            let grade_text = fields[fields.len() - 2];
            grade_text.parse::<u32>().map_err(|_| {
                format!("could not parse the grade \"{grade_text}\" on line {line_number}")
            })?
        } else {
            0
        };

        let mut coordinates = Vec::with_capacity(coordinate_count);
        for coordinate_text in &fields[..coordinate_count] {
            coordinates.push(coordinate_text.parse::<i32>().map_err(|_| {
                format!(
                    "could not parse the coordinate \"{coordinate_text}\" on line {line_number}"
                )
            })?);
        }

        let mut extent_mask = 0u32;
        for (axis, character) in extent_text.chars().enumerate() {
            if character == '1' {
                extent_mask |= 1u32 << axis;
            }
        }

        cubes.push((
            Cube::from_extent(Orthant::new(&coordinates), extent_mask),
            grade,
        ));
    }

    Ok(cubes)
}

fn main() {
    let arguments = Arguments::parse();
    let case_path = &arguments.case_path;

    let (backend, threads) = match arguments.backend {
        Backend::Sequential => (ExecutionBackend::Sequential, 1),
        Backend::Rayon => {
            rayon::ThreadPoolBuilder::new()
                .num_threads(arguments.threads)
                .build_global()
                .unwrap_or_else(|error| {
                    fail(&format!("could not build the rayon thread pool: {error}"))
                });
            (ExecutionBackend::Rayon, arguments.threads)
        }
    };

    let field = Field::new(arguments.modulus);
    let mut stages = Vec::new();

    let started = Instant::now();
    let read_cubes = match arguments.columns {
        Columns::Plain => read_orthants_csv(case_path)
            .map(CaseCubes::Orthants)
            .map_err(|error| error.to_string()),
        Columns::Graded => read_graded_orthants_csv(case_path)
            .map(CaseCubes::GradedOrthants)
            .map_err(|error| error.to_string()),
        Columns::Extent => read_extent_csv(case_path, false).map(CaseCubes::Cubes),
        Columns::GradedExtent => read_extent_csv(case_path, true).map(CaseCubes::Cubes),
    };
    let read_seconds = started.elapsed().as_secs_f64();
    let case_cubes = read_cubes
        .unwrap_or_else(|error| fail(&format!("could not read {}: {error}", case_path.display())));
    let cube_count = case_cubes.len();
    stages.push(stage("read", read_seconds, 0, cube_count));

    let started = Instant::now();
    let built = match case_cubes {
        CaseCubes::Orthants(orthants) => CubicalComplex::from_orthants(orthants, field),
        CaseCubes::GradedOrthants(orthants) => {
            CubicalComplex::from_graded_orthants(orthants, field)
        }
        CaseCubes::Cubes(cubes) => CubicalComplex::from_cubes(cubes, field),
    };
    let build_seconds = started.elapsed().as_secs_f64();
    let complex = built.unwrap_or_else(|error| {
        fail(&format!(
            "the cubes of {} describe no complex: {error}",
            case_path.display()
        ))
    });
    stages.push(stage("build", build_seconds, cube_count, cube_count));

    let ambient_dimension = complex.ambient_dimension();

    let mut matching_config = TemplateMatchingConfig::default();
    if let Some(dimension_cap) = arguments.max_critical_dimension {
        matching_config.maximum_critical_dimension = dimension_cap;
    }

    let started = Instant::now();
    let matching = TemplateMatching::from_config(matching_config, complex, &backend);
    let matching_seconds = started.elapsed().as_secs_f64();
    let critical_count = matching.critical_cells().len();
    stages.push(stage(
        "matching",
        matching_seconds,
        cube_count,
        critical_count,
    ));

    let started = Instant::now();
    let morse_complex = matching.construct_morse_complex(&backend);
    let morse_seconds = started.elapsed().as_secs_f64();
    let morse_count = morse_complex.cell_count() as usize;
    stages.push(stage("morse", morse_seconds, critical_count, morse_count));

    let started = Instant::now();
    let coreduction = Coreduction::new(morse_complex);
    let reduced_complex = coreduction.into_morse_complex();
    let coreduction_seconds = started.elapsed().as_secs_f64();
    let reduced_count = reduced_complex.cell_count() as usize;
    stages.push(stage(
        "coreduction",
        coreduction_seconds,
        morse_count,
        reduced_count,
    ));

    let started = Instant::now();
    let persistence = Persistence::of(&reduced_complex);
    let persistence_seconds = started.elapsed().as_secs_f64();
    let bar_count = persistence.bars().len();
    stages.push(stage(
        "persistence",
        persistence_seconds,
        reduced_count,
        bar_count,
    ));

    let betti: Vec<u32> = (0..=ambient_dimension)
        .map(|dimension| persistence.betti(dimension))
        .collect();
    let mut bar_counts = vec![0u32; ambient_dimension as usize + 1];
    let mut bars_finite = vec![0u32; ambient_dimension as usize + 1];
    let mut bars_essential = vec![0u32; ambient_dimension as usize + 1];
    for bar in persistence.bars() {
        let dimension = bar.dimension() as usize;
        match bar.death() {
            None => {
                bar_counts[dimension] += 1;
                bars_essential[dimension] += 1;
            }
            Some(death) if death > bar.birth() => {
                bar_counts[dimension] += 1;
                bars_finite[dimension] += 1;
            }
            Some(_) => {}
        }
    }

    let record = Record {
        tool: "chomp3rs",
        tool_version: CHOMP3RS_REV,
        config: Config {
            backend: arguments.backend.name(),
            threads,
            columns: arguments.columns.name(),
            max_critical_dimension: arguments.max_critical_dimension,
            modulus: arguments.modulus,
        },
        stages,
        answer: Answer {
            betti,
            bar_counts,
            bars_finite,
            bars_essential,
        },
    };

    println!(
        "{}",
        serde_json::to_string_pretty(&record).unwrap_or_else(|error| {
            fail(&format!("could not write the result record: {error}"))
        })
    );
}
