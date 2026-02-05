from cnc.formulas import (
    sfm_from_rpm,
    rpm_from_sfm,
    ipm_from_ipr,
    ipr_from_ipm,
)

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

print("\nCNC Feed & Speed Calculator")
print("1) SFM -> RPM")
print("2) RPM -> SFM")
print("3) IPR -> IPM (Lathe feed)")
print("4) IPM -> IPR (Lathe feed)")

choice = input("Choose 1-4: ").strip()

if choice in ("1", "2"):
    diameter = get_float("Tool diameter (inches): ")

    if choice == "1":
        sfm = get_float("Target SFM: ")
        rpm = rpm_from_sfm(diameter, sfm)
        print(f"\nRPM = {rpm:.0f}")
    else:
        rpm = get_float("RPM: ")
        sfm = sfm_from_rpm(diameter, rpm)
        print(f"\nSFM = {sfm:.2f}")

elif choice in ("3", "4"):
    rpm = get_float("RPM: ")

    if choice == "3":
        ipr = get_float("Feed (IPR): ")
        ipm = ipm_from_ipr(ipr, rpm)
        print(f"\nFeed = {ipm:.3f} IPM")
    else:
        ipm = get_float("Feed (IPM): ")
        ipr = ipr_from_ipm(ipm, rpm)
        print(f"\nFeed = {ipr:.4f} IPR")

else:
    print("Invalid choice. Run again and choose 1-4.")
