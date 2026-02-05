from cnc.formulas import sfm_from_rpm, rpm_from_sfm

def get_float(prompt: str) -> float:
    while True:
        try:
            val = float(input(prompt).strip())
            if val <= 0:
                print("Enter a number > 0.")
                continue
            return val
        except ValueError:
            print("Enter a valid number.")

print("CNC Feed & Speed Calculator")
print("1) SFM -> RPM")
print("2) RPM -> SFM")

choice = input("Choose 1 or 2: ").strip()

diameter = get_float("Tool diameter (inches): ")

if choice == "1":
    sfm = get_float("Target SFM: ")
    rpm = rpm_from_sfm(diameter, sfm)
    print(f"RPM = {rpm:.0f}")
elif choice == "2":
    rpm = get_float("RPM: ")
    sfm = sfm_from_rpm(diameter, rpm)
    print(f"SFM = {sfm:.2f}")
else:
    print("Invalid choice. Run again and choose 1 or 2.")
