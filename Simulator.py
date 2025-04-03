
import sys

class RISCVSimulator:
    def __init__(self):
        # Single 32-word memory (indices 0..31)
        self.memory = [0] * 32
        # Registers x0..x31
        self.registers = [0]*32
        # Program counter (word index into self.memory)
        self.pc = 0
        # Halt flag
        self.halted = False
        # Instruction count limit for safety
        self.max_instructions = 100000

    def load_program(self, bin_file):
        try:
            with open(bin_file, 'r') as f:
                i = 0
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) != 32:
                        print(f"Error at line {lineno}: Invalid instruction length ({len(line)} != 32)")
                        return False
                    if i >= 32:
                        print(f"Error at line {lineno}: Program too large for 32-word memory")
                        return False
                    # Convert binary string to int
                    try:
                        val = int(line, 2)
                    except ValueError:
                        print(f"Error at line {lineno}: Invalid binary string")
                        return False
                    self.memory[i] = val
                    i += 1
            return True
        except IOError:
            print("Error: Could not read binary file")
            return False

    def execute_program(self, trace_file):
        try:
            with open(trace_file, 'w') as out:
                instr_count = 0
                while not self.halted and instr_count < self.max_instructions:
                    if self.pc < 0 or self.pc >= 32:
                        print(f"Error: PC out of range ({self.pc}) at instruction count {instr_count}")
                        return False

                    instruction = self.memory[self.pc] & 0xffffffff
                    # Print trace
                    self.write_trace_line(out)

                    if not self.execute_instruction(instruction):
                        # An error was printed inside execute_instruction
                        return False

                    instr_count += 1

                if instr_count >= self.max_instructions:
                    print("Error: Maximum instruction count exceeded (infinite loop?)")
                    return False

                # After halt, dump memory
                self.write_memory_dump(out)

            return True
        except IOError:
            print("Error: Could not write trace file")
            return False

    def execute_instruction(self, instruction):
        opcode = instruction & 0x7f
        rd     = (instruction >> 7) & 0x1f
        funct3 = (instruction >> 12) & 0x7
        rs1    = (instruction >> 15) & 0x1f
        rs2    = (instruction >> 20) & 0x1f
        funct7 = (instruction >> 25) & 0x7f

        def imm_i():
            imm_12 = (instruction >> 20) & 0xfff
            if imm_12 & 0x800:
                imm_12 |= 0xfffff000
            return imm_12

        def imm_b():
            imm_12   = (instruction >> 31) & 0x1
            imm_10_5 = (instruction >> 25) & 0x3f
            imm_4_1  = (instruction >> 8) & 0xf
            imm_11   = (instruction >> 7) & 0x1
            val = (imm_12 << 12) | (imm_11 << 11) | (imm_10_5 << 5) | (imm_4_1 << 1)
            if val & 0x1000:
                val |= 0xffffe000
            return val

        def imm_j():
            imm_20   = (instruction >> 31) & 0x1
            imm_19_12= (instruction >> 12) & 0xff
            imm_11   = (instruction >> 20) & 0x1
            imm_10_1 = (instruction >> 21) & 0x3ff
            val = (imm_20 << 20) | (imm_19_12 << 12) | (imm_11 << 11) | (imm_10_1 << 1)
            if val & 0x100000:
                val |= 0xffe00000
            return val

        # R-type
        if opcode == 0x33:
            if funct3 == 0x0:
                if funct7 == 0x00:  # ADD
                    self.registers[rd] = (self.registers[rs1] + self.registers[rs2]) & 0xffffffff
                elif funct7 == 0x20:  # SUB
                    self.registers[rd] = (self.registers[rs1] - self.registers[rs2]) & 0xffffffff
                else:
                    print(f"Error: Unknown R-type funct7={funct7} at PC={self.pc}")
                    return False
            elif funct3 == 0x2:  # SLT
                s1 = self.registers[rs1] & 0xffffffff
                s2 = self.registers[rs2] & 0xffffffff
                # signed
                s1 = (s1 ^ 0x80000000) - 0x80000000
                s2 = (s2 ^ 0x80000000) - 0x80000000
                self.registers[rd] = 1 if s1 < s2 else 0
            elif funct3 == 0x5:
                shamt = self.registers[rs2] & 0x1f
                if funct7 == 0x00:  # SRL
                    self.registers[rd] = (self.registers[rs1] & 0xffffffff) >> shamt
                else:
                    print(f"Error: Unknown SRL funct7={funct7} at PC={self.pc}")
                    return False
            elif funct3 == 0x6:  # OR
                self.registers[rd] = (self.registers[rs1] | self.registers[rs2]) & 0xffffffff
            elif funct3 == 0x7:  # AND
                self.registers[rd] = (self.registers[rs1] & self.registers[rs2]) & 0xffffffff
            else:
                print(f"Error: Unknown R-type funct3={funct3} at PC={self.pc}")
                return False
            self.pc += 1

        # I-type arithmetic/logic
        elif opcode == 0x13:
            imm = imm_i()
            if funct3 == 0x0:  # ADDI
                self.registers[rd] = (self.registers[rs1] + imm) & 0xffffffff
            else:
                print(f"Error: Unknown I-type funct3={funct3} at PC={self.pc}")
                return False
            self.pc += 1

        # LW (opcode=0x03)
        elif opcode == 0x03:
            imm = imm_i()
            addr = (self.registers[rs1] + imm) & 0xffffffff
            if funct3 == 0x2:
                mem_idx = addr // 4
                if mem_idx < 0 or mem_idx >= 32:
                    print(f"Error: Memory access out of range (addr={hex(addr)}) at PC={self.pc}")
                    return False
                self.registers[rd] = self.memory[mem_idx]
            else:
                print(f"Error: Unsupported load funct3={funct3} at PC={self.pc}")
                return False
            self.pc += 1

        # JALR (opcode=0x67)
        elif opcode == 0x67:
            imm = imm_i()
            target = (self.registers[rs1] + imm) & 0xfffffffe
            ra = self.pc + 1
            self.registers[rd] = ra
            jump_word = target // 4
            if jump_word < 0 or jump_word >= 32:
                print(f"Error: JALR target out of range (addr={hex(target)}) at PC={self.pc}")
                return False
            self.pc = jump_word

        # S-type (SW) (opcode=0x23)
        elif opcode == 0x23:
            imm_11_5 = (instruction >> 25) & 0x7f
            imm_4_0  = (instruction >> 7) & 0x1f
            imm = (imm_11_5 << 5) | imm_4_0
            if imm & 0x800:
                imm |= 0xfffff000
            addr = (self.registers[rs1] + imm) & 0xffffffff
            if funct3 == 0x2:
                mem_idx = addr // 4
                if mem_idx < 0 or mem_idx >= 32:
                    print(f"Error: Memory store out of range (addr={hex(addr)}) at PC={self.pc}")
                    return False
                self.memory[mem_idx] = self.registers[rs2] & 0xffffffff
            else:
                print(f"Error: Unsupported store funct3={funct3} at PC={self.pc}")
                return False
            self.pc += 1

        # B-type (opcode=0x63)
        elif opcode == 0x63:
            offset = imm_b()
            # Virtual halt: beq zero, zero, 0
            if funct3 == 0x0 and rs1 == 0 and rs2 == 0 and offset == 0:
                self.halted = True
                return True

            taken = False
            reg1 = self.registers[rs1] & 0xffffffff
            reg2 = self.registers[rs2] & 0xffffffff
            s1 = (reg1 ^ 0x80000000) - 0x80000000
            s2 = (reg2 ^ 0x80000000) - 0x80000000

            if funct3 == 0x0:  # BEQ
                taken = (self.registers[rs1] == self.registers[rs2])
            elif funct3 == 0x1:  # BNE
                taken = (self.registers[rs1] != self.registers[rs2])
            else:
                print(f"Error: Unknown B-type funct3={funct3} at PC={self.pc}")
                return False

            if taken:
                self.pc += (offset // 4)
            else:
                self.pc += 1

        # JAL (opcode=0x6f)
        elif opcode == 0x6f:
            offset = imm_j()
            ra = self.pc + 1
            self.registers[rd] = ra
            self.pc += (offset // 4)

        else:
            print(f"Error: Unknown opcode={hex(opcode)} at PC={self.pc}")
            return False

        # x0 is always 0
        self.registers[0] = 0
        return True

    def write_trace_line(self, out):
        """
        After each instruction, write:
          PC_in_binary x0_in_binary x1_in_binary ... x31_in_binary
        """
        pc_bin = format(self.pc*4, '032b')
        regs_bin = [format(r & 0xffffffff, '032b') for r in self.registers]
        out.write(pc_bin + " " + " ".join(regs_bin) + "\n")

    def write_memory_dump(self, out):
        """
        After the virtual halt, print all 32 words of memory in binary (one per line).
        """
        for word in self.memory:
            out.write(format(word & 0xffffffff, '032b') + "\n")

def main():
    if len(sys.argv) != 3:
        print("Usage: python simulator.py <input_binary_file> <trace_output_file>")
        return

    input_bin = sys.argv[1]
    output_trace = sys.argv[2]

    sim = RISCVSimulator()
    if not sim.load_program(input_bin):
        return

    if sim.execute_program(output_trace):
        print("Simulation completed successfully")

if __name__ == "__main__":
    main()
