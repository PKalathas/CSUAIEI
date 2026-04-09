public class Main {
    public static void main(String[] args) {

//        Human myHuman = new Human();
//        Human myHuman2 = new Human(5);
        Human myFarmer = new Farmer();
        Knight myKnight = new Knight();

        System.out.println("Human");
//        myHuman.print();

//        System.out.println(" ");
//        System.out.println("Farmer");
//        myFarmer.print();

        System.out.println(" ");
        System.out.println("Knight");
        myKnight.print();
        int ret = (myKnight.print(3));
        System.out.println(ret);
    }
}